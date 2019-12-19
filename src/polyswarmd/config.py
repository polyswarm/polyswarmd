import json
import logging
import os
import redis
import time
import yaml

from consul.base import Timeout
from requests import HTTPError
from requests_futures.sessions import FuturesSession
from web3 import HTTPProvider, Web3
from web3.exceptions import MismatchedABI
from web3.middleware import geth_poa_middleware

from polyswarmd.services.artifact.ipfs import IpfsServiceClient
from polyswarmd.services.artifact.service import ArtifactServices
from polyswarmd.services.auth.service import AuthService
from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.services.ethereum.service import EthereumService
from polyswarmd.status import Status
from polyswarmd.utils import camel_case_to_snake_case

logger = logging.getLogger(__name__)

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']

# Allow interfacing with contract versions in this range
SUPPORTED_CONTRACT_VERSIONS = {
    'ArbiterStaking': ((1, 2, 0), (1, 3, 0)),
    'BountyRegistry': ((1, 6, 0), (1, 7, 0)),
    'ERC20Relay': ((1, 2, 0), (1, 4, 0)),
    'OfferRegistry': ((1, 2, 0), (1, 3, 0)),
}

DEFAULT_FALLBACK_SIZE = 10 * 1024 * 1024


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
        from polyswarmd.views.eth import ZERO_ADDRESS
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
                logger.error(
                    'Invalid version specified for contract %s, require major.minor.patch as string',
                    self.name
                )
                raise ValueError('Invalid contract version reported')

            if len(version) != 3 or not min_version <= version < max_version:
                logger.error(
                    "Received %s version %s.%s.%s, but expected version between %s.%s.%s and %s.%s.%s ",
                    self.name, *version, *min_version, *max_version
                )
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
    def __init__(
        self, name, eth_uri, chain_id, w3, nectar_token, bounty_registry, arbiter_staking,
        erc20_relay, offer_registry, offer_multisig, free
    ):
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
        return cls(
            name, eth_uri, chain_id, w3, contract_configs.get('NectarToken'),
            contract_configs.get('BountyRegistry'), contract_configs.get('ArbiterStaking'),
            contract_configs.get('ERC20Relay'), contract_configs.get('OfferRegistry'),
            contract_configs.get('OfferMultiSig'), free
        )

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
        expected_contracts = [
            'NectarToken', 'BountyRegistry', 'ArbiterStaking', 'ERC20Relay', 'OfferRegistry',
            'OfferMultiSig'
        ]
        contract_configs = {}

        base_key = key.rsplit('/', 1)[0] + '/'
        filter_k = {base_key + x for x in ('homechain', 'sidechain', 'config')}

        while True:
            kvs = [
                x for x in fetch_from_consul_or_wait(consul_client, base_key, recurse=True)
                if x.get('Key') not in filter_k
            ]

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
        if self.chain_id != int(self.w3.version.network):
            raise ValueError(
                'Chain ID mismatch, expected %s got %s', self.chain_id, int(self.w3.version.network)
            )

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
        self.arbiter_staking.bind(
            address=self.bounty_registry.contract.functions.staking().call(), persistent=True
        )


class Config(object):
    session = FuturesSession()

    def __init__(
        self, community, ipfs_uri, artifact_limit, auth_uri, require_api_key, homechain_config,
        sidechain_config, trace_transactions, profiler_enabled, redis_client,
        fallback_max_artifact_size, max_artifact_size
    ):
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
        self.fallback_max_artifact_size = fallback_max_artifact_size
        self.max_artifact_size = int(max_artifact_size)
        self.status = Status(community)
        self.status.register_services(self.__create_services())

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
        fallback_max_artifact_size = config.get('fallback_max_artifact_size', DEFAULT_FALLBACK_SIZE)
        max_artifact_size = config.get(
            'max_artifact_size', os.environ.get('MAX_ARTIFACT_SIZE', DEFAULT_FALLBACK_SIZE)
        )
        return cls(
            commmunity, ipfs_uri, artifact_limit, auth_uri, require_api_key, homechain_config,
            sidechain_config, trace_transactions, profiler_enabled, redis_client,
            fallback_max_artifact_size, max_artifact_size
        )

    @classmethod
    def from_config_file_search(cls):
        for location in CONFIG_LOCATIONS:
            location = os.path.abspath(os.path.expanduser(location))
            filename = os.path.join(location, 'polyswarmd.yml')
            if os.path.isfile(filename):
                return cls.from_config_file(filename)

        raise OSError('Config file not found')

    @classmethod
    def auto(cls):
        return cls.from_config_file_search()

    def __create_services(self):
        services = [*self.__create_ethereum_services(), self.__create_artifact_service()]
        if self.auth_uri:
            services.append(self.__create_auth_services())
        return services

    def __create_artifact_service(self):
        return ArtifactServices(self.artifact_client, self.session)

    def __create_ethereum_services(self):
        return [EthereumService(name, chain, self.session) for name, chain in self.chains.items()]

    def __create_auth_services(self):
        return AuthService(self.auth_uri, self.session)

    def __validate(self):
        self.__validate_community()
        self.__validate_auth()
        self.__validate_services()
        self.__validate_artifacts()

    def __validate_community(self):
        if not self.community:
            raise ValueError('No community specified')

    def __validate_auth(self):
        if self.require_api_key and not self.auth_uri:
            raise ValueError('API keys required but no API key service URI specified')

    def __validate_services(self):
        for service in self.status.services:
            try:
                service.test_reachable()
            except HTTPError:
                raise ValueError(f'{service.name} not reachable, is correct URI specified?')

    def __validate_artifacts(self):
        self.__validate_artifact_limit()

    def __validate_artifact_limit(self):
        if self.artifact_limit < 1 or self.artifact_limit > 256:
            raise ValueError(
                'Artifact limit must be greater than 0 and cannot exceed contract limit of 256'
            )

    def __validate_artifact_fallback_size(self):
        if self.fallback_max_artifact_size < 1:
            raise ValueError('Fall back max artifact size must be greater than 0')
