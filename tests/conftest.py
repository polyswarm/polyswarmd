"""
   isort:skip_file
"""
import random
import os
import pytest
from unittest.mock import patch

from .utils import read_chain_cfg
import web3.datastructures

import web3.manager

import web3.eth
import web3.contract


def let(obj, **kwargs):
    for attr, val in kwargs.items():
        setattr(obj, attr, val)
    return obj


# a list of function patches to be applied prior `import polyswarmd`
PRE_INIT_PATCHES = (
    # don't both with patching gevent methods inside pytest
    patch('gevent.monkey.patch_all', return_value=None),
    # # fake out the underlying ipfshttpclient connect
    # set `POLY_WORK` to be 'testing' (if not already set)
    patch('os.getenv', lambda *args, **kwargs: 'testing' if args[0] == 'POLY_WORK' else os.getenv)
)

for pa in PRE_INIT_PATCHES:
    pa.start()

# NOTE polyswarmd is structured such that merely importing a package in the `polyswarmd` namespace will
# raise an exception. Fixing this (e.g moving stuff outta src/polyswarmd/__init__.py) has been on the
# todo list for some time, but for now, we just patch up methods which have unsafe side effects to
# run unit tests without side-effects.
import polyswarmd as _polyswarmd  # noqa
from polyswarmd.app import app as _app  # noqa

for pa in PRE_INIT_PATCHES:
    pa.stop()


@pytest.fixture(scope='session')
def app():
    return _app


@pytest.fixture(scope='session')
def client(app):
    app.config['TESTING'] = True
    yield app.test_client()


@pytest.fixture(params=['home', 'side'], scope='session')
def chain_config(request):
    return read_chain_cfg(request.param)
@pytest.fixture(params=['home', 'side'], scope='session')
def chains(request, app):
    return app.config['POLYSWARMD'].chains[request.param]


@pytest.fixture
def chain_id(): return 1337
@pytest.fixture(scope='session')
def community(): return 'gamma'
@pytest.fixture(scope='session')
def base_nonce(): return 1248924
@pytest.fixture
def balances(token_address): return {token_address: 12345}
@pytest.fixture(scope='session')
def token_address(): return '0x4B1867c484871926109E3C47668d5C0938CA3527'
@pytest.fixture
def gas_limit(): return 94040201
@pytest.fixture
def block_number(token_address): return 5197


@pytest.fixture
def bounty_parameters():
    return {
        'arbiter_lookback_range': 100,
        'arbiter_vote_window': 100,
        'assertion_bid_maximum': 1000000000000000000,
        'assertion_bid_minimum': 62500000000000000,
        'assertion_fee': 31250000000000000,
        'assertion_reveal_window': 10,
        'bounty_amount_minimum': 100,
        'bounty_fee': 62500000000000000,
        'max_duration': 100
    }



@pytest.fixture
def contract_fns(token_address, balances, bounty_parameters):
    """mock out values of contract functions

    NOTE: if the function shares a name with a patched function here, that value will be used, e.g
    `contract_fns` does *not* distinguish between contracts.
    """

    fn_table = {}

    def patch_contract(func):

        def driver(self, *args):
            return func(*args)

        fn_table[func.__name__] = driver
        return driver

    @patch_contract
    def balanceOf(address):
        return balances[address]

    @patch_contract
    def withdrawableBalanceOf(address):
        return balances[address]

    @patch_contract
    def bountyFee():
        return bounty_parameters['bounty_fee']

    @patch_contract
    def assertionFee():
        return bounty_parameters['assertion_fee']

    @patch_contract
    def assertionRevealWindow():
        return bounty_parameters['assertion_reveal_window']

    @patch_contract
    def arbiterVoteWindow():
        return bounty_parameters['arbiter_vote_window']

    @patch_contract
    def ASSERTION_BID_ARTIFACT_MAXIMUM():
        return bounty_parameters['assertion_bid_maximum']

    @patch_contract
    def ASSERTION_BID_ARTIFACT_MINIMUM():
        return bounty_parameters['assertion_bid_minimum']

    for name, value in bounty_parameters.items():
        fn_table[name.upper()] = lambda s: value

    return fn_table


@pytest.fixture
def web3_blocking_values(balances, token_address, block_number, chain_id, gas_limit):
    """mock values for `web3.manager.request_blocking`"""
    return {
        'eth_blockNumber':
            block_number,
        'eth_call':
            lambda data, to: '0x' + '0'*64,
        'eth_getBalance':
            lambda token_address, block: balances[token_address],
        'eth_getBlockByNumber':
            lambda *_: web3.datastructures.AttributeDict({'gasLimit': gas_limit}),
        'eth_getTransactionCount':
            lambda token_address, block: balances[token_address],
        'eth_syncing':
            False,
        'net_version':
            chain_id
    }


@pytest.fixture(autouse=True)
def mock_polyswarmd(monkeypatch):
    """Mock polyswarmd functions which call out to external services"""
    monkeypatch.setattr(_polyswarmd.config.service.Service, "test_reachable", lambda *_: True)
    monkeypatch.setattr(
        _polyswarmd.services.ethereum.service.EthereumService, "check_chain_id", lambda *_: True
    )


@pytest.fixture(autouse=True)
def mock_w3(monkeypatch, contract_fns, web3_blocking_values):
    """Mock out underlying w3py functions so that tests can be run sans-geth"""
    _ContractFunction_call = web3.contract.ContractFunction.call

    def mock_call(w3_cfn, *args, **kwargs):
        name = w3_cfn.fn_name
        if name not in contract_fns:
            print("WARNING: Using non-mocked contract function: ", name)
        fn = contract_fns.get(name, _ContractFunction_call)
        return fn(w3_cfn, *w3_cfn.args)

    def mock_request_blocking(self, method, params):
        mock = web3_blocking_values[method]
        return mock(*params) if callable(mock) else mock

    monkeypatch.setattr(web3.manager.RequestManager, "request_blocking", mock_request_blocking)
    monkeypatch.setattr(web3.contract.ContractFunction, "call", mock_call)
