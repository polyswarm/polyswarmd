import json
import logging
import os
import threading
import time
import requests

from urllib.parse import urlparse

import yaml
import redis
from consul import Consul
from consul.base import Timeout
from web3 import Web3, HTTPProvider
from web3.exceptions import MismatchedABI
from web3.middleware import geth_poa_middleware

from polyswarmd.artifacts.ipfs import IpfsServiceClient
from polyswarmd.utils import camel_case_to_snake_case
from polyswarmd.rpc import EthereumRpc

logger = logging.getLogger(__name__)

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']

# Allow interfacing with contract versions in this range
SUPPORTED_CONTRACT_VERSIONS = {
    'ArbiterStaking': ((1, 2, 0), (1, 3, 0)),
    'BountyRegistry': ((1, 2, 0), (1, 5, 0)),
    'ERC20Relay': ((1, 1, 0), (1, 3, 0)),
    'OfferRegistry': ((1, 2, 0), (1, 3, 0)),
}


def is_service_reachable(session, uri, is_ethereum=False):
    if is_ethereum:
        # parity does not support GET, so use POST.
        # Using application/json is to cover geth as well.
        session.headers.update({'Content-Type': 'application/json'})
        r = session.post(uri)
    else:
        r = session.get(uri)

    # check if futures session or normal
    if hasattr(r, "result"):
        r = r.result()

    return r is not None and r.status_code == 200


def wait_for_service(session, uri):
    logger.info('Waiting for service at %s', uri)

    while True:
        if is_service_reachable(session, uri):
            logger.info('%s available, continuing', uri)
            return
        else:
            logger.info('%s not available, sleeping', uri)
            time.sleep(1)


def fetch_from_consul_or_wait(client, key, recurse=False, index=0):
    logger.info('Fetching key: %s', key)
    while True:
        try:
            index, data = client.kv.get(key, recurse=recurse, index=index, wait='2m')
            if data is not None:
                return data
        except Timeout:
            logger.info('Consul up but key %s not available, retrying...', key)
            continue


def wait_for_consul_key_deletion(client, key, recurse=False, index=0):
    logger.info('Watching key: %s', key)
    while True:
        try:
            index, data = client.kv.get(key, recurse=recurse, index=index, wait='2m')
            if data is None:
                return
        except Timeout:
            logger.info('Consul key %s still valid', key)
            continue


class ContractConfig(object):
    def __init__(self, w3, name, abi, address=None):
        self.name = name
        self.w3 = w3
        self.abi = abi
        self.address = address

        self.contract = None

        # Eager bind if address provided
        if address:
            self.bind(persistent=True)

    def bind(self, address=None, persistent=False):
        from polyswarmd.eth import ZERO_ADDRESS
        if self.contract:
            return self.contract

        if not address:
            address = self.address

        if not address:
            raise ValueError('No address provided to bind to')

        ret = self.w3.eth.contract(address=self.w3.toChecksumAddress(address), abi=self.abi)

        supported_versions = SUPPORTED_CONTRACT_VERSIONS.get(self.name)
        if supported_versions is not None and address != ZERO_ADDRESS:
            min_version, max_version = supported_versions
            try:
                version = tuple(int(s) for s in ret.functions.VERSION().call().split('.'))
            except MismatchedABI:
                logger.error('Expected version but no version reported for contract %s', self.name)
                raise ValueError('No contract version reported')
            except ValueError:
                logger.error('Invalid version specified for contract %s, require major.minor.patch as string',
                             self.name)
                raise ValueError('Invalid contract version reported')

            if len(version) != 3 or not min_version <= version < max_version:
                logger.error("Received %s version %s.%s.%s, but expected version between %s.%s.%s and %s.%s.%s ", self.name, *version, *min_version, *max_version)
                raise ValueError('Unsupported contract version')

        if persistent:
            self.contract = ret

        return ret

    @classmethod
    def from_json(cls, w3, name, contract, config):
        if 'abi' not in contract:
            return None

        abi = contract.get('abi')

        # XXX: OfferMultiSig doesn't follow this convention, but we don't bind that now anyway
        address = config.get(camel_case_to_snake_case(name) + '_address')

        return cls(w3, name, abi, address)


class ChainConfig(object):
    session = requests.Session()

    def __init__(self, name, eth_uri, chain_id, w3, nectar_token, bounty_registry, arbiter_staking, erc20_relay,
                 offer_registry, offer_multisig, free):
        self.name = name
        self.eth_uri = eth_uri
        self.chain_id = chain_id
        self.w3 = w3
        self.nectar_token = nectar_token
        self.bounty_registry = bounty_registry
        self.arbiter_staking = arbiter_staking
        self.erc20_relay = erc20_relay
        self.offer_registry = offer_registry
        self.offer_multisig = offer_multisig
        self.rpc = EthereumRpc(self)

        self.free = free
        self.config_filename = ''

        self.__validate()
        self.__bind_child_contracts()

    @classmethod
    def from_contract_configs(cls, name, eth_uri, chain_id, w3, contract_configs, free):
        return cls(name, eth_uri, chain_id, w3, contract_configs.get('NectarToken'),
                   contract_configs.get('BountyRegistry'), contract_configs.get('ArbiterStaking'),
                   contract_configs.get('ERC20Relay'), contract_configs.get('OfferRegistry'),
                   contract_configs.get('OfferMultiSig'), free)

    @classmethod
    def from_config_file(cls, name, filename):
        with open(filename, 'r') as f:
            config = yaml.safe_load(f)

        eth_uri = config.get('eth_uri')
        chain_id = config.get('chain_id')
        free = config.get('free', False)
        w3 = Web3(HTTPProvider(eth_uri))
        w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        contract_configs = {}

        contracts_dir = os.path.join(os.path.dirname(filename), 'contracts')
        for root, dirs, files in os.walk(contracts_dir):
            for file in files:
                with open(os.path.join(root, file), 'r') as f:
                    contract = json.load(f)

                name = os.path.splitext(file)[0]
                contract_config = ContractConfig.from_json(w3, name, contract, config)
                if not contract_config:
                    continue

                contract_configs[contract_config.name] = contract_config

        ret = cls.from_contract_configs(name, eth_uri, chain_id, w3, contract_configs, free)
        ret.config_filename = filename

        return ret

    @classmethod
    def from_consul(cls, consul_client, name, key):
        config = fetch_from_consul_or_wait(consul_client, key).get('Value')
        if config is None:
            raise ValueError(f'Invalid chain config for chain {name}')

        config = json.loads(config.decode('utf-8'))

        eth_uri = config.get('eth_uri')
        chain_id = config.get('chain_id')
        free = config.get('free', False)
        w3 = Web3(HTTPProvider(eth_uri))
        w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        # TODO schema check json
        expected_contracts = ['NectarToken', 'BountyRegistry', 'ArbiterStaking', 'ERC20Relay', 'OfferRegistry',
                              'OfferMultiSig']
        contract_configs = {}

        base_key = key.rsplit('/', 1)[0] + '/'
        filter_k = {base_key + x for x in ('homechain', 'sidechain', 'config')}

        while True:
            kvs = [x for x in fetch_from_consul_or_wait(consul_client, base_key, recurse=True)
                   if x.get('Key') not in filter_k]

            for kv in kvs:
                contract = json.loads(kv.get('Value').decode('utf-8'))
                name = kv.get('Key').rsplit('/', 1)[-1]
                contract_config = ContractConfig.from_json(w3, name, contract, config)
                if not contract_config:
                    continue

                contract_configs[contract_config.name] = contract_config

            if all([c in contract_configs for c in expected_contracts]):
                break

            logger.info('Key present but not all contracts deployed, retrying...')
            time.sleep(1)

        return cls.from_contract_configs(name, eth_uri, chain_id, w3, contract_configs, free)

    def __validate(self):
        if not is_service_reachable(self.session, self.eth_uri, is_ethereum=True):
            raise ValueError('Ethereum not reachable, is correct URI specified?')

        if self.chain_id != int(self.w3.version.network):
            raise ValueError('Chain ID mismatch, expected %s got %s', self.chain_id, int(self.w3.version.network))

        if not self.nectar_token or not self.nectar_token.contract:
            raise ValueError('Invalid NectarToken contract or address')

        if not self.bounty_registry or not self.bounty_registry.contract:
            raise ValueError('Invalid BountyRegistry contract or address')

        if not self.erc20_relay or not self.erc20_relay.contract:
            raise ValueError('Invalid ERC20Relay contract or address')

        # Child contracts not bound yet, but should be defined
        if not self.arbiter_staking:
            raise ValueError('Invalid ArbiterStaking contract')

        # Offer contracts only live on homechain
        if self.name == 'home':
            if not self.offer_registry or not self.offer_registry.contract:
                raise ValueError('Invalid OfferRegistry contract or address')

            if not self.offer_multisig:
                raise ValueError('Invalid OfferMultiSig contract')

    def __bind_child_contracts(self):
        self.arbiter_staking.bind(address=self.bounty_registry.contract.functions.staking().call(), persistent=True)


class Config(object):
    session = requests.Session()

    def __init__(self, community, ipfs_uri, artifact_limit, auth_uri, require_api_key, homechain_config,
                 sidechain_config, trace_transactions, profiler_enabled, redis_client):
        self.community = community
        # For now, there is no other option than IpfsServiceClient, but this will eventually be configurable
        self.artifact_client = IpfsServiceClient(ipfs_uri)
        self.artifact_limit = artifact_limit
        self.auth_uri = auth_uri
        self.require_api_key = require_api_key
        self.chains = {
            'home': homechain_config,
            'side': sidechain_config,
        }
        self.config_filename = ''
        self.trace_transactions = trace_transactions
        self.profiler_enabled = profiler_enabled
        self.redis = redis_client

        self.__validate()

    @classmethod
    def from_config_file(cls, filename):
        homechain_config = ChainConfig.from_config_file('home', filename)
        sidechain_config = ChainConfig.from_config_file('side', filename)

        with open(filename, 'r') as f:
            config = yaml.safe_load(f)

        commmunity = config.get('community')
        ipfs_uri = config.get('ipfs_uri')
        artifact_limit = config.get('artifact_limit', 256)
        auth_uri = config.get('auth_uri', os.environ.get('AUTH_URI'))
        require_api_key = auth_uri is not None
        trace_transactions = config.get('trace_transactions', True)
        profiler_enabled = config.get('profiler_enabled', False)
        redis_uri = config.get('redis_uri', os.environ.get('REDIS_URI', None))
        redis_client = redis.Redis.from_url(redis_uri) if redis_uri else None
        return cls(commmunity, ipfs_uri, artifact_limit, auth_uri, require_api_key, homechain_config, sidechain_config,
                   trace_transactions, profiler_enabled, redis_client)

    @classmethod
    def from_config_file_search(cls):
        for location in CONFIG_LOCATIONS:
            location = os.path.abspath(os.path.expanduser(location))
            filename = os.path.join(location, 'polyswarmd.yml')
            if os.path.isfile(filename):
                return Config.from_config_file(filename)

        raise OSError('Config file not found')

    @classmethod
    def from_consul(cls):
        consul_uri = os.environ.get('CONSUL')
        consul_token = os.environ.get('CONSUL_TOKEN', None)

        wait_for_service(cls.session, consul_uri)

        u = urlparse(consul_uri)
        consul_client = Consul(host=u.hostname, port=u.port, scheme=u.scheme, token=consul_token)

        community = os.environ['POLY_COMMUNITY_NAME']
        homechain_config = ChainConfig.from_consul(consul_client, 'home', f'chain/{community}/homechain')
        sidechain_config = ChainConfig.from_consul(consul_client, 'side', f'chain/{community}/sidechain')

        base_key = f'chain/{community}'
        config = fetch_from_consul_or_wait(consul_client, base_key + '/config').get('Value')
        if config is None:
            raise ValueError('Invalid global config')

        config = json.loads(config.decode('utf-8'))

        ipfs_uri = config.get('ipfs_uri')
        artifact_limit = config.get('artifact_limit', 256)
        auth_uri = config.get('auth_uri', os.environ.get('AUTH_URI'))
        require_api_key = auth_uri is not None
        trace_transactions = config.get('trace_transactions', True)
        profiler_enabled = config.get('profiler_enabled', False)
        redis_uri = config.get('redis_uri', os.environ.get('REDIS_URI', None))
        redis_client = redis.Redis.from_url(redis_uri) if redis_uri else None

        ret = cls(community, ipfs_uri, artifact_limit, auth_uri, require_api_key, homechain_config, sidechain_config,
                  trace_transactions, profiler_enabled, redis_client)

        # Watch for key deletion, if config is deleted die and restart with new config
        def watch_for_config_deletion(consul_client, key):
            wait_for_consul_key_deletion(consul_client, key, recurse=True)
            logger.fatal('Config change detected, exiting')

            # sys.exit is caught by flask, we want to tear down immediately though
            os._exit(0)

        t = threading.Thread(target=watch_for_config_deletion, args=(consul_client, base_key))
        t.start()

        return ret

    @classmethod
    def auto(cls):
        if os.environ.get('CONSUL'):
            return cls.from_consul()
        else:
            return cls.from_config_file_search()

    def __validate(self):
        # We expect IPFS and API key service to be up already
        if not is_service_reachable(self.session, self.artifact_client.reachable_endpoint):
            raise ValueError(f'{self.artifact_client.name} not reachable, is correct URI specified?')

        if self.artifact_limit < 1 or self.artifact_limit > 256:
            raise ValueError('Artifact limit must be greater than 0 and cannot exceed contract limit of 256')

        if self.auth_uri and not is_service_reachable(self.session, f"{self.auth_uri}/communities/public"):
            raise ValueError('API key service not reachable, is correct URI specified?')

        if self.require_api_key and not self.auth_uri:
            raise ValueError('API keys required but no API key service URI specified')

        if not self.community:
            raise ValueError('No community specified')
