"""
This project is intended to provide an easy and efficient way to lend and/or borrow tokens and XTZ on Tezos blockchain.

<small>Built with SmartPy 0.14.0</small>
"""

import smartpy as sp


class Error:
    """The enum used for the contract related errors."""

    ACCESS_DENIED = "ERR_ACCESS_DENIED"
    """The contract function is not accessible for the sender."""

    ILLEGAL_ARGUMENT = "ERR_ILLEGAL_ARGUMENT"
    """The corresponding argument value is invalid."""

    ILLEGAL_TX_AMOUNT = "ERR_ILLEGAL_TX_AMOUNT"
    """The corresponding transaction has incorrect tezos amount."""

    PAUSED = "ERR_PAUSED"
    """The contract is paused."""



class TokenType:
    """The enum used for the contract token types."""

    XTZ  = sp.nat(0)
    """Native Tezos token."""

    FA12 = sp.nat(1)
    """Fungible Asset (FA1.2)."""

    FA20 = sp.nat(2)
    """Multi-Asset (FA2)."""



# Token structure.
# 
TToken = sp.TRecord(
    name = sp.TString,       # token name
    address = sp.TAddress,   # token address
    type = sp.TNat,          # token type: TokenType.XTZ or TokenType.FA12 or TokenType.FA20
    token_id = sp.TNat,      # token id
    decimals = sp.TNat,      # decimals
)



def transfer_tokens(sender, receiver, amount, token):
    """Help function to transfer tokens.

    Args:
        sender (address): source address
        receiver (address): destination address
        amount (nat): amount of tokens
        token_id (nat): deposit token ID
        token (TToken): token information
    """
    sp.if (token.type == TokenType.FA12):
        param_values = sp.record(from_ = sender, to_ = receiver, value = amount)
        param_type = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        sp.transfer(param_values, sp.mutez(0), sp.contract(param_type, token.address, entry_point="transfer").open_some())
    sp.else:
        param_values = [sp.record(from_ = sender, txs = [sp.record(to_ = receiver, token_id = token.token_id, amount = amount)])]
        param_type = sp.TList(sp.TRecord(from_ = sp.TAddress, txs = sp.TList(sp.TRecord(amount = sp.TNat, to_ = sp.TAddress, token_id = sp.TNat).layout(("to_", ("token_id", "amount"))))))
        sp.transfer(param_values, sp.mutez(0), sp.contract(param_type, token.address, entry_point='transfer').open_some())



class LendTez(sp.Contract):
    """The contract is a storage for p2p credit deals and provides service functionality to make such deals.

    There is the storage:
    Args:
        pause (bool): indicates that creating loan requests and making credit deals is disabled
        baker (option): baker address or _None_
        admins (set): list of admin addresses
        time (pair): time bounds for credit deals
        ntoken (nat): last token ID
        tokens (big_map): supported tokens (key is token ID)
        nloan (nat): last loan request ID
        loans (big_map): map of loan requests (key is loan request ID)
        ndeal (nat): last credit deal ID
        deals (big_map): map of credit deals (key is credit deal ID)
    """

    def __init__(self, creator):
        self.creator = creator

        self.init(
            pause = False,
            baker = sp.none,
            admins = sp.set([creator]),
            time = sp.record(min = sp.nat(7 * 86400), max = sp.nat(180 * 86400)),
            ntoken = sp.nat(0),
            tokens = sp.big_map(),
            nloan = sp.nat(0),
            loans = sp.big_map(),
            ndeal = sp.nat(0),
            deals = sp.big_map(),
        )


    @sp.entry_point
    def default(self):
        """Support tezos transfer to the contract address."""
        pass


    @sp.entry_point
    def withdraw(self, params):
        """(Admins only) Transfer XTZ (except locked collateral) from the contract address.
        
        Args:
            to (address): destination address
            id (nat): token ID of XTZ
            amount (mutez): XTZ amount
        Raises:
            `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.to, sp.TAddress)
        sp.set_type(params.id, sp.TNat)
        sp.set_type(params.amount, sp.TNat)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.data.tokens.contains(params.id), message = Error.ILLEGAL_ARGUMENT + ":id")
        sp.verify(self.data.tokens[params.id].type == TokenType.XTZ, message = Error.ILLEGAL_ARGUMENT + ":id")
        sp.verify(params.amount > 0, message = Error.ILLEGAL_ARGUMENT + ":amount")
        sp.verify(sp.utils.mutez_to_nat(sp.balance) >= (self.data.tokens[params.id].locked_amount + params.amount), message = Error.ILLEGAL_ARGUMENT + ":amount")
        sp.send(params.to, sp.utils.nat_to_mutez(params.amount))


    @sp.entry_point
    def add_admin(self, params):
        """(Admins only) Add an admin address to the list of admin addresses.
        
        Args:
            address (address): new admin address
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.address, sp.TAddress)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(~self.data.admins.contains(params.address), message = Error.ILLEGAL_ARGUMENT + ":address")
        self.data.admins.add(params.address)


    @sp.entry_point
    def remove_admin(self, params):
        """(Admins only) Remove an admin address from the list of admin addresses.

        Args:
            address (address): admin address
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.address, sp.TAddress)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.creator != params.address, message = Error.ILLEGAL_ARGUMENT + ":address")
        sp.verify(self.data.admins.contains(params.address), message = Error.ILLEGAL_ARGUMENT + ":address")
        self.data.admins.remove(params.address)


    @sp.entry_point
    def delegate(self, params):
        """(Admins only) Set a baker for the contract.

        Args:
            baker (option): baker address or _None_
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.baker, sp.TOption(sp.TKeyHash))
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.data.baker != params.baker, message = Error.ILLEGAL_ARGUMENT + ":baker")
        self.data.baker = params.baker
        sp.set_delegate(params.baker)


    @sp.entry_point
    def pause(self, params):
        """(Admins only) Disable/enable making of new loan requests and new deals.

        Args:
            pause (bool): _True_ or _False_
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.pause, sp.TBool)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.data.pause != params.pause, message = Error.ILLEGAL_ARGUMENT + ":pause")
        self.data.pause = params.pause


    @sp.entry_point
    def set_time(self, params):
        """(Admins only) Set time bounds for credit deals.

        Args:
            min (nat): minimum deal duration in seconds
            max (nat): maximum deal duration in seconds
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params, sp.TRecord(min = sp.TNat, max = sp.TNat))
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.data.time != params, message = Error.ILLEGAL_ARGUMENT + ":min,max")
        sp.verify((params.min > 0) & (params.min <= params.max), message = Error.ILLEGAL_ARGUMENT + ":min")
        self.data.time = params


    @sp.entry_point
    def add_token(self, params):
        """(Admins only) Add supported token.

        Args:
            name (string): token name
            address (address): token address
            type (nat): token type (TokenType.XTZ or TokenType.FA12 or TokenType.FA20)
            token_id (nat): token id for the corresponding token address
            decimals (nat): decimals
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params, TToken)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify((params.type == TokenType.XTZ) | (params.type == TokenType.FA12) | (params.type == TokenType.FA20), message = Error.ILLEGAL_ARGUMENT + ":type")
        self.data.tokens[self.data.ntoken] = sp.record(
            name = params.name,
            address = params.address,
            type = params.type,
            token_id = params.token_id,
            decimals = params.decimals,
            locked_amount = 0,
            active = True
        )
        self.data.ntoken += 1


    @sp.entry_point
    def set_token_active(self, params):
        """(Admins only) Set active status for supported token.

        Args:
            id (nat): token id
            active (bool): active status (a token can not be a part of a loan request if active=_False_)
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.id, sp.TNat)
        sp.set_type(params.active, sp.TBool)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.admins.contains(sp.sender), message = Error.ACCESS_DENIED)
        sp.verify(self.data.tokens.contains(params.id), message = Error.ILLEGAL_ARGUMENT + ":id")
        sp.verify(self.data.tokens[params.id].active != params.active, message = Error.ILLEGAL_ARGUMENT + ":active")
        self.data.tokens[params.id].active = params.active


    @sp.entry_point
    def add_loan(self, params):
        """Create a new loan request.
        
        The corresponding transaction amount has to include deposit, if the deposit is XTZ.

        Args:
            loan_token_id (nat): loan token ID
            loan_amount (nat): requested amount of tokens
            reward (nat): amount of tokens as creditor's reward 
            deposit_token_id (nat): deposit token ID
            deposit_amount (nat): deposit amount of tokens
            time (nat): credit deal duration in seconds
            validity (option): loan request expire date or None
        Raises:
            `OD_PAUSED`, `OD_ILLEGAL_TX_AMOUNT`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.loan_token_id, sp.TNat)
        sp.set_type(params.loan_amount, sp.TNat)
        sp.set_type(params.reward, sp.TNat)
        sp.set_type(params.deposit_token_id, sp.TNat)
        sp.set_type(params.deposit_amount, sp.TNat)
        sp.set_type(params.time, sp.TNat)
        sp.set_type(params.validity, sp.TOption(sp.TTimestamp))
        sp.verify(~self.data.pause, message = Error.PAUSED)
        sp.verify(self.data.tokens.contains(params.loan_token_id), message = Error.ILLEGAL_ARGUMENT + ":loan_token_id")
        sp.verify(self.data.tokens[params.loan_token_id].active, message = Error.ILLEGAL_ARGUMENT + ":loan_token")
        sp.verify(params.loan_amount > 0, message = Error.ILLEGAL_ARGUMENT + ":loan_amount")
        sp.verify(params.loan_token_id != params.deposit_token_id , message = Error.ILLEGAL_ARGUMENT + ":deposit_token")
        sp.verify(self.data.tokens.contains(params.deposit_token_id), message = Error.ILLEGAL_ARGUMENT + ":deposit_token_id")
        sp.verify(self.data.tokens[params.deposit_token_id].active, message = Error.ILLEGAL_ARGUMENT + ":deposit_token")
        sp.verify((params.time >= self.data.time.min) & (params.time <= self.data.time.max), message = Error.ILLEGAL_ARGUMENT + ":time")
        sp.verify((params.validity == sp.none) | (params.validity > sp.some(sp.now)), message = Error.ILLEGAL_ARGUMENT + ":validity")

        deposit_token = sp.local("deposit_token", self.data.tokens[params.deposit_token_id])
        sp.if (deposit_token.value.type == TokenType.XTZ):
            sp.verify(params.deposit_amount == sp.utils.mutez_to_nat(sp.amount), message = Error.ILLEGAL_TX_AMOUNT)
        sp.else:
            sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
            sp.if (params.deposit_amount > 0):
                transfer_tokens(sender = sp.sender, receiver = sp.self_address, amount = params.deposit_amount, token = deposit_token.value)
        self.data.tokens[params.deposit_token_id].locked_amount += params.deposit_amount
        self.data.nloan += 1
        self.data.loans[self.data.nloan] = sp.record(
            ts = sp.now,
            borrower = sp.sender,
            loan_token_id = params.loan_token_id,
            loan_amount = params.loan_amount,
            reward = params.reward,
            deposit_token_id = params.deposit_token_id,
            deposit_amount = params.deposit_amount,
            time = params.time,
            validity = params.validity
        )


    @sp.entry_point
    def cancel_loan(self, params):
        """Cancel sender's loan request, the deposit of the loan is returned to the sender.

        Args:
            id (nat): loan request ID
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.id, sp.TNat)
        sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
        sp.verify(self.data.loans.contains(params.id), message = Error.ILLEGAL_ARGUMENT + ":id")
        loan = sp.local("loan", self.data.loans[params.id])
        sp.verify((sp.sender == loan.value.borrower) | self.data.admins.contains(sp.sender), Error.ACCESS_DENIED)
        self.refund_deposit(receiver = loan.value.borrower, token_id = loan.value.deposit_token_id, amount = loan.value.deposit_amount)
        del self.data.loans[params.id]


    @sp.entry_point
    def make_deal(self, params):
        """Make a credit deal, the sender has to approve the corresponding token transfer early.

        Args:
            id (nat): loan request ID
        Raises:
            `OD_PAUSED`, `OD_ILLEGAL_TX_AMOUNT`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.id, sp.TNat)
        sp.verify(~self.data.pause, message = Error.PAUSED)
        sp.verify(self.data.loans.contains(params.id), message = Error.ILLEGAL_ARGUMENT + ":id")
        loan = sp.local("loan", self.data.loans[params.id])
        sp.verify(loan.value.borrower != sp.sender, Error.ILLEGAL_ARGUMENT + ":sender")
        sp.verify((loan.value.validity == sp.none) | (loan.value.validity > sp.some(sp.now)), message = Error.ILLEGAL_ARGUMENT + ":now")
        loan_token = sp.local("loan_token", self.data.tokens[loan.value.loan_token_id])
        sp.if (loan_token.value.type == TokenType.XTZ):
            sp.verify(loan.value.loan_amount == sp.utils.mutez_to_nat(sp.amount), message = Error.ILLEGAL_TX_AMOUNT)
            sp.send(loan.value.borrower, sp.amount)
        sp.else:
            sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
            transfer_tokens(sender = sp.sender, receiver = loan.value.borrower, amount = loan.value.loan_amount, token = loan_token.value)
        self.data.ndeal += 1
        self.data.deals[self.data.ndeal] = sp.record(
            ts = sp.now,
            borrower = loan.value.borrower,
            creditor = sp.sender,
            loan_token_id = loan.value.loan_token_id,
            loan_amount = loan.value.loan_amount,
            reward = loan.value.reward,
            exp = sp.now.add_seconds(sp.to_int(loan.value.time)),
            deposit_token_id = loan.value.deposit_token_id,
            deposit_amount = loan.value.deposit_amount,
        )
        del self.data.loans[params.id]


    @sp.entry_point
    def close_deal(self, params):
        """Close a deal by borrower or creditor/admins.

        If a deal is closed by borrower, the tokens are sent to the creditor and the borrower gets back the deposit;
        if a deal timed out and it's closed by the creditor or admins, the creditor gets the deposit.

        Args:
            id (nat): credit deal ID
        Raises:
            `OD_ILLEGAL_TX_AMOUNT`, `OD_ACCESS_DENIED`, `OD_ILLEGAL_ARGUMENT`
        """
        sp.set_type(params.id, sp.TNat)
        sp.verify(self.data.deals.contains(params.id), message = Error.ILLEGAL_ARGUMENT + ":id")
        deal = sp.local("deal", self.data.deals[params.id])
        sp.verify((sp.sender == deal.value.borrower) | (sp.sender == deal.value.creditor) | self.data.admins.contains(sp.sender), Error.ACCESS_DENIED)
        deposit_receiver = sp.local('deposit_receiver', sp.self_address)
        sp.if sp.sender == deal.value.borrower:
            loan_token = sp.local("loan_token", self.data.tokens[deal.value.loan_token_id])
            sp.if (loan_token.value.type == TokenType.XTZ):
                sp.verify((deal.value.loan_amount + deal.value.reward) == sp.utils.mutez_to_nat(sp.amount), message = Error.ILLEGAL_TX_AMOUNT)
                sp.send(deal.value.creditor, sp.amount)
            sp.else:
                sp.verify(sp.amount == sp.mutez(0), message = Error.ILLEGAL_TX_AMOUNT)
                transfer_tokens(sender = deal.value.borrower, receiver = deal.value.creditor, amount = (deal.value.loan_amount + deal.value.reward), token = loan_token.value)
            deposit_receiver.value = deal.value.borrower
        sp.else:
            sp.verify(deal.value.exp < sp.now, message = Error.ACCESS_DENIED)
            deposit_receiver.value = deal.value.creditor
        self.refund_deposit(receiver = deposit_receiver.value, token_id = deal.value.deposit_token_id, amount = deal.value.deposit_amount)
        del self.data.deals[params.id]


    def refund_deposit(self, receiver, token_id, amount):
        """Help function to send deposit.

        Args:
            receiver (address): destination address
            token_id (nat): deposit token ID
            amount (nat): deposit amount of tokens
        """
        sp.if amount > 0:
            deposit_token = sp.local("deposit_token", self.data.tokens[token_id])
            sp.if (deposit_token.value.type == TokenType.XTZ):
                sp.send(receiver, sp.utils.nat_to_mutez(amount))
            sp.else:
                transfer_tokens(sender = sp.self_address, receiver = receiver, amount = amount, token = deposit_token.value)
            self.data.tokens[token_id].locked_amount = sp.as_nat(self.data.tokens[token_id].locked_amount - amount)



#########################################################################################################

CREATOR_ADDRESS = "tz1fE6hEiRFa9ZHJeZrccNKsGW7jdxfe9vcv"

# Tests
@sp.add_test(name = "LendTez")
def test():
    creator = sp.address(CREATOR_ADDRESS)
    admin = sp.test_account("Admin")
    userA = sp.test_account("UserA")
    userB = sp.test_account("UserB")
    userC = sp.test_account("UserC")
    DAY = 86400
    INITIAL_BALANCE = 1_000_000_000
    c1 = LendTez(creator)
    c1.set_initial_balance(sp.mutez(INITIAL_BALANCE))
    scenario = sp.test_scenario()
    scenario.h1("LendTez tests")
    scenario += c1


    scenario.h1("Admins")
    scenario.h2("add_admin()")
    c1.add_admin(address=userA.address).run(sender = creator, amount=sp.mutez(1), valid = False)
    c1.add_admin(address=userA.address).run(sender = userA, valid = False)
    c1.add_admin(address=admin.address).run(sender = creator)
    c1.add_admin(address=admin.address).run(sender = creator, valid = False)
    c1.add_admin(address=userA.address).run(sender = admin)
    scenario.h2("remove_admin()")
    c1.remove_admin(address=userA.address).run(sender = admin, amount=sp.mutez(1), valid = False)
    c1.remove_admin(address=admin.address).run(sender = userB, valid = False)
    c1.remove_admin(address=creator).run(sender = admin, valid = False)
    c1.remove_admin(address=userA.address).run(sender = admin)
    c1.remove_admin(address=userA.address).run(sender = admin, valid = False)


    scenario.h1("Delegate")
    scenario.h2("delegate()")
    keyHash = sp.key_hash("tz1fwnfJNgiDACshK9avfRfFbMaXrs3ghoJa")
    voting_powers = {keyHash : 0}
    c1.delegate(baker=sp.some(keyHash)).run(sender = admin, voting_powers = voting_powers, amount=sp.mutez(1), valid = False)
    c1.delegate(baker=sp.some(keyHash)).run(sender = userB, voting_powers = voting_powers, valid = False)
    c1.delegate(baker=sp.some(keyHash)).run(sender = admin, voting_powers = voting_powers)
    c1.delegate(baker=sp.some(keyHash)).run(sender = admin, voting_powers = voting_powers, valid = False)
    scenario.verify_equal(c1.baker, sp.some(keyHash))
    c1.delegate(baker=sp.none).run(sender = admin)


    scenario.h1("Time")
    scenario.h2("set_time()")
    c1.set_time(sp.record(min=1*DAY, max=366*DAY)).run(sender = creator, amount=sp.mutez(1), valid = False)
    c1.set_time(sp.record(min=3*DAY, max=60*DAY)).run(sender = userA, valid = False)
    c1.set_time(sp.record(min=0*DAY, max=366*DAY)).run(sender = creator, valid = False)
    c1.set_time(sp.record(min=180*DAY, max=7*DAY)).run(sender = creator, valid = False)
    c1.set_time(sp.record(min=1*DAY, max=366*DAY)).run(sender = admin)
    c1.set_time(sp.record(min=1*DAY, max=366*DAY)).run(sender = creator, valid = False)


    scenario.h1("Tokens")
    tXTZ = sp.record(name="XTZ", address=c1.address, type=0, token_id=0, decimals=6)
    tBTC = sp.record(name="_BTC", address=sp.address("tz1oBTCoMEtsXm3QxA7FmMU2Qh7xzsUoBTCo"), type=1, token_id=0, decimals=8)
    tETH = sp.record(name="_ETH", address=sp.address("tz1oETHo1otsXm3QxA7FmMU2Qh7xzsGoETHo"), type=1, token_id=0, decimals=18)
    tXRP = sp.record(name="_XRP", address=sp.address("tz1oXRPoMEtsXm3QxA7FmMU2Qh7xzsSoXRPo"), type=1, token_id=0, decimals=12)
    fake_tBTC = sp.record(name="_BTC", address=tETH.address, type=1, token_id=0,  decimals=8)
    fake_tBTC_id=123
    scenario.h2("add_token()")
    c1.add_token(tBTC).run(sender = creator, amount=sp.mutez(1), valid = False)
    c1.add_token(tETH).run(sender = userA, valid = False)
    c1.add_token(tXTZ).run(sender = creator)
    tXTZ_id = 0
    c1.add_token(tBTC).run(sender = creator)
    tBTC_id = 1
    c1.add_token(tETH).run(sender = admin)
    tETH_id = 2
    c1.add_token(tXRP).run(sender = admin)
    tXRP_id = 3
    scenario.h2("set_token_active()")
    c1.set_token_active(id=tBTC_id, active=False).run(sender = creator, amount=sp.mutez(1), valid = False)
    c1.set_token_active(id=tXTZ_id, active=False).run(sender = userA, valid = False)
    c1.set_token_active(id=fake_tBTC_id, active=False).run(sender = creator, valid = False)
    c1.set_token_active(id=tXRP_id, active=True).run(sender = admin, valid = False)
    c1.set_token_active(id=tXRP_id, active=False).run(sender = admin)


    scenario.h1("Loans")
    scenario.h2("add_loan()")
    scenario.p("Loan token is not active (error):")
    c1.add_loan(loan_token_id=tXRP_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tXTZ_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(15_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Loan token is not supported (error):")
    c1.add_loan(loan_token_id=fake_tBTC_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tXTZ_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(15_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Loan amount is 0 (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=0, reward=1000,
        deposit_token_id=tXTZ_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(15_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Loan_token = deposit_token (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tETH_id, deposit_amount=10_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Deposit token name is not active (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tXRP_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Deposit token is not supported (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=fake_tBTC_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Time is too small (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tBTC_id, deposit_amount=15_000_000, time=1, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Time is too big (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tBTC_id, deposit_amount=15_000_000, time=456*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Loan request is expired (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tBTC_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.some(sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Incorrect XTZ deposit amount (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tXTZ_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(1_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("XTZ transaction amount > 0 (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tBTC_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(15_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Loan request in tokens with deposit in XTZ with validity:")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=10_000, reward=1000,
        deposit_token_id=tXTZ_id, deposit_amount=15_000_000, time=7*DAY, validity=sp.some(sp.timestamp_from_utc(2022, 5, 14, 0, 0, 0))
        ).run(sender=userA, amount=sp.mutez(15_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    scenario.p("Loan request in tokens with deposit in XTZ without validity:")
    c1.add_loan(loan_token_id=tBTC_id, loan_amount=20_000, reward=200,
        deposit_token_id=tXTZ_id, deposit_amount=100_000_000, time=14*DAY, validity=sp.none
        ).run(sender=userB, amount=sp.mutez(100_000_000), now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0))
    scenario.p("Loan request in tokens with deposit in tokens without validity:")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=2000, reward=200,
        deposit_token_id=tBTC_id, deposit_amount=200_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    scenario.h2("cancel_loan()")
    scenario.p("XTZ transaction amount > 0 (error):")
    c1.cancel_loan(id=1).run(sender = userA, amount=sp.mutez(1), valid = False)
    scenario.p("Incorrect loan request id (error):")
    c1.cancel_loan(id=123).run(sender = userA, valid = False)
    scenario.p("Sender is not loan request creator (error):")
    c1.cancel_loan(id=1).run(sender = userB, valid = False)
    scenario.p("Cancel loan requests:")
    c1.cancel_loan(id=1).run(sender = userA)
    c1.cancel_loan(id=2).run(sender = admin)
    c1.cancel_loan(id=3).run(sender = userA)


    scenario.h1("Deals")
    scenario.p("Add loan requests:")
    c1.add_loan(loan_token_id=tBTC_id, loan_amount=1000, reward=100,
        deposit_token_id=tXTZ_id, deposit_amount=100_000, time=7*DAY, validity=sp.some(sp.timestamp_from_utc(2022, 5, 10, 0, 0, 0))
        ).run(sender=userA, amount=sp.mutez(100_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    c1.add_loan(loan_token_id=tETH_id, loan_amount=2000, reward=200,
        deposit_token_id=tBTC_id, deposit_amount=200_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    c1.add_loan(loan_token_id=tXTZ_id, loan_amount=3000, reward=300,
        deposit_token_id=tETH_id, deposit_amount=300_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    c1.add_loan(loan_token_id=tETH_id, loan_amount=2000, reward=200,
        deposit_token_id=tBTC_id, deposit_amount=200_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    # scenario.h2("remove_token() with locked amount > 0")
    # c1.remove_token(n=tXTZ.n).run(sender = creator, valid = False)
    # c1.remove_token(n=tBTC.n).run(sender = admin, valid = False)
    scenario.h2("make_deal()")
    scenario.p("Incorrect loan request id (error):")
    c1.make_deal(id=1).run(sender=userB, valid = False)
    scenario.p("Borrower can't be creditor (error):")
    c1.make_deal(id=4).run(sender=userA, valid = False)
    scenario.p("Loan request is expired (error):")
    c1.make_deal(id=4).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 10, 0, 0, 0), valid = False)
    scenario.p("Requested XTZ amount is incorrect (error):")
    c1.make_deal(id=6).run(sender=userB, amount=sp.mutez(10), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("XTZ amount is incorrect (error):")
    c1.make_deal(id=4).run(sender=userB, amount=sp.mutez(10), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Making correct deals:")
    c1.make_deal(id=4).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    c1.make_deal(id=5).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    c1.make_deal(id=6).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), amount=sp.mutez(3000))
    c1.make_deal(id=7).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    scenario.h2("close_deal()")
    scenario.p("Incorrect deal id (error):")
    c1.close_deal(id=0).run(sender=userA, valid = False)
    scenario.p("Incorrect user (error):")
    c1.close_deal(id=1).run(sender=userC, valid = False)
    scenario.p("Creditor can't close deal because it's not expired (error):")
    c1.close_deal(id=1).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0), valid = False)
    scenario.p("Borrower can't close deal because XTZ amount is incorrect (error):")
    c1.close_deal(id=3).run(sender=userA, amount=sp.mutez(3000), now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0), valid = False)
    scenario.p("Borrower can't close deal because XTZ amount has to be 0 (error):")
    c1.close_deal(id=1).run(sender=userA, amount=sp.mutez(1), now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0), valid = False)
    scenario.p("Close deals:")
    scenario.p("Borrower returns tokens:")
    c1.close_deal(id=1).run(sender=userA, now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0))
    scenario.p("Borrower returns XTZ:")
    c1.close_deal(id=3).run(sender=userA, amount=sp.mutez(3300), now=sp.timestamp_from_utc(2022, 5, 2, 0, 0, 0))
    scenario.p("Creditor closes deal:")
    c1.close_deal(id=2).run(sender=userB, now=sp.timestamp_from_utc(2022, 5, 12, 0, 0, 0))
    scenario.p("Admin closes deal:")
    c1.close_deal(id=4).run(sender=admin, now=sp.timestamp_from_utc(2022, 5, 12, 0, 0, 0))


    scenario.h1("Pause")
    scenario.h2("pause()")
    c1.pause(pause=True).run(sender = admin, amount=sp.mutez(1), valid = False)
    c1.pause(pause=False).run(sender = userA, valid = False)
    c1.pause(pause=False).run(sender = admin, valid = False)
    c1.pause(pause=True).run(sender = admin)
    scenario.p("Creating new loan request is not possible (error):")
    c1.add_loan(loan_token_id=tETH_id, loan_amount=1000, reward=100,
        deposit_token_id=tXTZ_id, deposit_amount=15000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(15000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0), valid = False)
    scenario.p("Making deal is not possible (error):")
    c1.make_deal(id=1).run(sender=userC, valid = False)
    c1.pause(pause=False).run(sender = admin)


    scenario.h1("Withdraw")
    c1.add_loan(loan_token_id=tBTC_id, loan_amount=1000, reward=100,
        deposit_token_id=tXTZ_id, deposit_amount=10_000_000, time=7*DAY, validity=sp.none
        ).run(sender=userA, amount=sp.mutez(10_000_000), now=sp.timestamp_from_utc(2022, 5, 1, 0, 0, 0))
    scenario.h2("withdraw()")
    scenario.p("Sender is not admin (error):")
    c1.withdraw(to=userA.address, id=tXTZ_id, amount=1).run(sender = userA, valid = False)
    scenario.p("Token name is not XTZ (error):")
    c1.withdraw(to=admin.address, id=tBTC_id, amount=1).run(sender = admin, valid = False)
    scenario.p("Amount is 0 (error):")
    c1.withdraw(to=admin.address, id=tXTZ_id, amount=0).run(sender = admin, valid = False)
    scenario.p("Amount is too big (error):")
    c1.withdraw(to=admin.address, id=tXTZ_id, amount=sp.utils.mutez_to_nat(c1.balance)+1).run(sender = admin, valid = False)
    scenario.p("Successful withdrawal:")
    c1.withdraw(to=admin.address, id=tXTZ_id, amount=INITIAL_BALANCE).run(sender = creator)
    scenario.p("Amount is too big (error):")
    c1.withdraw(to=admin.address, id=tXTZ_id, amount=1).run(sender = creator, valid = False)
    scenario.verify(c1.balance == sp.utils.nat_to_mutez(c1.data.tokens[tXTZ_id].locked_amount))



sp.add_compilation_target("lendtez", LendTez(CREATOR_ADDRESS))
