from web3.module import Module

MAX_GAS_LIMIT = 50000000
GAS_MULTIPLIER = 1.5
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
TRANSFER_SIGNATURE_HASH = 'a9059cbb'
HOME_TIMEOUT = 60
SIDE_TIMEOUT = 10


class Debug(Module):
    ERROR_SELECTOR = '08c379a0'

    def getTransactionError(self, txhash):
        if not txhash.startswith('0x'):
            txhash = '0x' + txhash

        trace = self.web3.manager.request_blocking(
            'debug_traceTransaction',
            [txhash, {
                'disableStorage': True,
                'disableMemory': True,
                'disableStack': True,
            }]
        )

        if not trace.get('failed'):
            logger.error('Transaction receipt indicates failure but trace succeeded')
            return 'Transaction receipt indicates failure but trace succeeded'

        # Parse out the revert error code if it exists
        # See https://solidity.readthedocs.io/en/v0.4.24/control-structures.html#error-handling-assert-require-revert-and-exceptions  # noqa: E501
        # Encode as if a function call to `Error(string)`
        rv = HexBytes(trace.get('returnValue'))

        # Trim off function selector for "Error"
        if not rv.startswith(HexBytes(Debug.ERROR_SELECTOR)):
            logger.error(
                'Expected revert encoding to begin with %s, actual is %s', Debug.ERROR_SELECTOR,
                rv[:4].hex()
            )
            return 'Invalid revert encoding'
        rv = rv[4:]

        error = decode_abi(['string'], rv)[0]
        return error.decode('utf-8')


def get_gas_limit():
    gas_limit = MAX_GAS_LIMIT
    if app.config['CHECK_BLOCK_LIMIT']:
        gas_limit = g.chain.w3.eth.getBlock('latest').gasLimit

    if app.config['CHECK_BLOCK_LIMIT'] and gas_limit >= MAX_GAS_LIMIT:
        app.config['CHECK_BLOCK_LIMIT'] = False

    return gas_limit


def build_transaction(call, nonce):
    # Only a problem for fresh chains
    gas_limit = get_gas_limit()
    options = {
        'nonce': nonce,
        'chainId': int(g.chain.chain_id),
        'gas': gas_limit,
    }

    gas = gas_limit
    if g.chain.free:
        options["gasPrice"] = 0
    else:
        try:
            gas = int(call.estimateGas({'from': g.eth_address, **options}) * GAS_MULTIPLIER)
        except ValueError as e:
            logger.debug('Error estimating gas, using default: %s', e)

    options['gas'] = min(gas_limit, gas)
    logger.debug('options: %s', options)

    return call.buildTransaction(options)

@cache.memoize(1)
def get_txpool():
    return g.chain.w3.txpool.inspect


def decode_all(raw_txs):
    return [rlp.decode(bytes.fromhex(raw_tx), sedes=ConstantinopleTransaction) for raw_tx in raw_txs]


def is_withdrawal(tx):
    """
    Take a transaction and return True if that transaction is a withdrawal
    """
    data = tx.data[4:]
    to = g.chain.w3.toChecksumAddress(tx.to.hex())
    sender = g.chain.w3.toChecksumAddress(tx.sender.hex())

    try:
        target, amount = decode_abi(['address', 'uint256'], data)
    except InsufficientDataBytes:
        logger.warning('Transaction by %s to %s is not a withdrawal', sender, to)
        return False

    target = g.chain.w3.toChecksumAddress(target)
    if (
        tx.data.startswith(HexBytes(TRANSFER_SIGNATURE_HASH)) and
        g.chain.nectar_token.address == to and tx.value == 0 and
        tx.network_id == app.config["POLYSWARMD"].chains['side'].chain_id and
        target == g.chain.erc20_relay.address and amount > 0
    ):
        logger.info('Transaction is a withdrawal by %s for %d NCT', sender, amount)
        return True

    logger.warning('Transaction by %s to %s is not a withdrawal', sender, to)
    return False


def events_from_transaction(txhash, chain):
    config = app.config['POLYSWARMD']
    trace_transactions = config.eth.trace_transactions
    if trace_transactions:
        try:
            Debug.attach(g.chain.w3, 'debug')
        except AttributeError:
            # We've already attached, just continue
            pass

    # TODO: Check for out of gas, other
    timeout = gevent.Timeout(HOME_TIMEOUT if chain == 'home' else SIDE_TIMEOUT)
    timeout.start()

    try:
        while True:
            tx = g.chain.w3.eth.getTransaction(txhash)
            if tx is not None and tx.blockNumber:
                # fix suggested by https://github.com/ethereum/web3.js/issues/2917#issuecomment-507154487
                while g.chain.w3.eth.blockNumber - tx.blockNumber < 1:
                    gevent.sleep(1)
                receipt = g.chain.w3.eth.getTransactionReceipt(txhash)
                break
            gevent.sleep(1)

    except gevent.Timeout as t:
        if t is not timeout:
            raise
        logging.error('Transaction %s: timeout waiting for receipt', bytes(txhash).hex())
        return {'errors': [f'transaction {bytes(txhash).hex()}: timeout during wait for receipt']}
    except Exception:
        logger.exception(
            'Transaction %s: error while fetching transaction receipt',
            bytes(txhash).hex()
        )
        return {
            'errors': [
                f'transaction {bytes(txhash).hex()}: unexpected error while fetching transaction receipt'
            ]
        }
    finally:
        timeout.cancel()

    txhash = bytes(txhash).hex()
    if not receipt:
        return {'errors': [f'transaction {txhash}: receipt not available']}
    if receipt.gasUsed == MAX_GAS_LIMIT:
        return {'errors': [f'transaction {txhash}: out of gas']}
    if receipt.status != 1:
        if trace_transactions:
            error = g.chain.w3.debug.getTransactionError(txhash)
            logger.error('Transaction %s failed with error message: %s', txhash, error)
            return {
                'errors': [
                    f'transaction {txhash}: transaction failed at block {receipt.blockNumber}, error: {error}'
                ]
            }
        else:
            return {
                'errors': [
                    f'transaction {txhash}: transaction failed at block {receipt.blockNumber}, check parameters'
                ]
            }

    # This code builds the return value from the list of (CONTRACT, [HANDLER, ...])
    # a HANDLER is a tuple of (RESULT KEY, EXTRACTION CLASS). RESULT KEY is the key that will be used in the result,
    # EXTRACTION CLASS is any class which inherits from `EventLogMessage'.
    # NOTE EXTRACTION CLASS's name is used to id the contract event, which is then pass to it's own `extract` fn
    # XXX The `extract' method is a conversion function also used to convert events for WebSocket consumption.
    contracts: List[Tuple[Any, List[Tuple[str, Type[messages.EventLogMessage]]]]]
    contracts = [
        (g.chain.nectar_token.contract.events, [('transfers', messages.Transfer)]),
        (
            g.chain.bounty_registry.contract.events, [('bounties', messages.NewBounty),
                                                      ('assertions', messages.NewAssertion),
                                                      ('votes', messages.NewVote),
                                                      ('reveals', messages.RevealedAssertion)]
        ),
        (
            g.chain.arbiter_staking.contract.events, [('withdrawals', messages.NewWithdrawal),
                                                      ('deposits', messages.NewDeposit)]
        )
    ]

    if g.chain.offer_registry.contract:
        offer_msig = g.chain.offer_multi_sig.bind(ZERO_ADDRESS)
        contracts.append((
            g.chain.offer_registry.contract.events,
            [('offers_initialized', messages.InitializedChannel)]
        ))
        contracts.append((
            offer_msig.events, [('offers_opened', messages.OpenedAgreement),
                                ('offers_canceled', messages.CanceledAgreement),
                                ('offers_joined', messages.JoinedAgreement),
                                ('offers_closed', messages.ClosedAgreement),
                                ('offers_settled', messages.StartedSettle),
                                ('offers_challenged', messages.SettleStateChallenged)]
        ))
    ret: Dict[str, List[Dict[str, Any]]] = {}
    for contract, processors in contracts:
        for key, extractor in processors:
            filter_event = extractor.contract_event_name
            contract_event = contract[filter_event]
            if not contract_event:
                logger.warning("No contract event for: %s", filter_event)
                continue
            # Now pull out the pertinent logs from the transaction receipt
            abi = contract_event._get_event_abi()
            for log in receipt['logs']:
                try:
                    event_log = get_event_data(abi, log)
                    if event_log:
                        ret[key] = [extractor.extract(event_log['args'])]
                    break
                except MismatchedABI:
                    continue

    return ret


@cache.memoize(1)
def bounty_fee(bounty_registry):
    return bounty_registry.functions.bountyFee().call()


@cache.memoize(1)
def assertion_fee(bounty_registry):
    return bounty_registry.functions.assertionFee().call()


@cache.memoize(1)
def bounty_amount_min(bounty_registry):
    return bounty_registry.functions.BOUNTY_AMOUNT_MINIMUM().call()


@cache.memoize(1)
def assertion_bid_min(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MINIMUM().call()


@cache.memoize(1)
def assertion_bid_max(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MAXIMUM().call()


@cache.memoize(1)
def staking_total_max(arbiter_staking):
    return arbiter_staking.functions.MAXIMUM_STAKE().call()


@cache.memoize(1)
def staking_total_min(arbiter_staking):
    return arbiter_staking.functions.MINIMUM_STAKE().call()
