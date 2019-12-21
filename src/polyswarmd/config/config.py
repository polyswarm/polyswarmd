import json
import logging
import os
from typing import Dict, Any, Optional, List, Set, Tuple
from urllib.parse import urlparse

import redis
import time
import yaml

from consul.base import Timeout, Consul
from redis import Redis
from requests import HTTPError
from requests_futures.sessions import FuturesSession
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from polyswarmd.config.contract import Contract
from polyswarmd.exceptions import MissingConfigValueError
from polyswarmd.services.artifact.client import AbstractArtifactServiceClient
from polyswarmd.services.artifact.service import ArtifactServices
from polyswarmd.services.auth.service import AuthService
from polyswarmd.services.consul.service import ConsulService
from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.services.ethereum.service import EthereumService
from polyswarmd.config.status import Status

logger = logging.getLogger(__name__)

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']
DEFAULT_FALLBACK_SIZE = 10 * 1024 * 1024
EXPECTED_CONTRACTS = ['NectarToken', 'BountyRegistry', 'ArbiterStaking', 'ERC20Relay', 'OfferRegistry', 'OfferMultiSig']


class DictConfig:
    @staticmethod
    def retrieve_value(key: str, loaded: Dict[str, Any]) -> Any:
        value = loaded.get(key)
        if not value:
            raise MissingConfigValueError(key)

        return value

    @staticmethod
    def retrieve_sub_config(key: str, loaded: Dict[str, Any]) -> Dict[str, Any]:
        return loaded.get(key, {})


class ArtifactConfig(DictConfig):
    client: AbstractArtifactServiceClient
    limit: int
    fallback_max_size: int
    max_size: int

    def __init__(self, configuration: Dict[str, Any]):
        self.populate_client(configuration)
        self.populate_fallback_artifact_size(configuration)
        self.populate_limit(configuration)
        self.populate_max__size(configuration)

    def populate_limit(self, artifact: Dict[str, Any]):
        try:
            self.limit = self.retrieve_value('limit', artifact)
        except MissingConfigValueError:
            self.limit = 256

    def populate_max__size(self, artifact: Dict[str, Any]):
        try:
            self.max_size = self.retrieve_value('max_size', artifact)
        except MissingConfigValueError:
            self.max_size = int(os.environ.get('MAX_ARTIFACT_SIZE', DEFAULT_FALLBACK_SIZE))

    def populate_fallback_artifact_size(self, artifact: Dict[str, Any]):
        try:
            self.fallback_max_size = self.retrieve_value('fallback_max_size', artifact)
        except MissingConfigValueError:
            self.fallback_max_size = DEFAULT_FALLBACK_SIZE

    def populate_client(self, artifact: Dict[str, Any]):
        client_specification = self.retrieve_value('client', artifact)
        self.client = self.load_client_from_spec(client_specification)

    def load_client_from_spec(self, client_specification: Dict[str, Any]) -> AbstractArtifactServiceClient:
        module_name = self.retrieve_value('module', client_specification)
        class_name = self.retrieve_value('class', client_specification)
        settings = self.retrieve_value('settings', client_specification)
        return self.load_client_with_settings(module_name, class_name, settings)

    def load_client_with_settings(self, module_name: str, class_name: str, settings: Dict[str, Any]) -> AbstractArtifactServiceClient:
        pass


class AuthConfig(DictConfig):
    uri: Optional[str]

    def __init__(self, auth: Dict[str, Any]):
        self.populate_uri(auth)

    def populate_uri(self, auth: Dict[str, Any]):
        try:
            self.uri = self.retrieve_value("uri", auth)
        except MissingConfigValueError:
            pass

    @property
    def require_api_key(self):
        return self.uri is not None


class ChainConfig(DictConfig):
    name: str
    eth_uri: str
    chain_id: int
    free: bool
    w3: Web3
    nectar_token: Contract
    bounty_registry: Contract
    erc20_relay: Contract
    arbiter_staking: Contract
    offer_registry: Contract
    offer_multisig: Contract
    rpc: EthereumRpc

    def __init__(self, chain: Dict[str, Any]):
        self.populate(chain)
        self.load_web3(self.eth_uri)
        self.load_contracts(chain)
        self.load_rpc()
        self.__validate()

    def populate(self, chain: Dict[str, Any]):
        self.populate_name(chain)
        self.populate_eth_uri(chain)
        self.populate_chain_id(chain)
        self.populate_free(chain)

    def populate_name(self, chain: Dict[str, Any]):
        self.name = self.retrieve_value('name', chain)

    def populate_free(self, chain: Dict[str, Any]):
        try:
            self.free = self.retrieve_value('free', chain)
        except MissingConfigValueError:
            self.free = False

    def populate_chain_id(self, chain: Dict[str, Any]):
        self.chain_id = self.retrieve_value('chain_id', chain)

    def populate_eth_uri(self, chain: Dict[str, Any]):
        self.eth_uri = self.retrieve_value('eth_uri', chain)

    def load_web3(self, eth_uri: str):
        self.w3 = Web3(HTTPProvider(eth_uri))
        self.w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    def load_rpc(self):
        self.rpc = EthereumRpc(self)

    def load_contracts(self, chain: Dict[str, Any]):
        contracts = self.create_contracts(chain)
        self.nectar_token = self.retrieve_value('NectarToken', contracts)
        self.bounty_registry = self.retrieve_value('BountyRegistry', contracts)
        self.erc20_relay = self.retrieve_value('ERC20Relay', contracts)
        self.arbiter_staking = self.retrieve_value('ArbiterStaking', contracts)
        self.offer_registry = self.retrieve_value('OfferRegistry', contracts)
        self.offer_multisig = self.retrieve_value('OfferMultiSig', contracts)
        self.__bind_child_contracts()

    def create_contracts(self, chain: Dict[str, Any]) -> Dict[str, Contract]:
        return {name: Contract.from_json(self.w3, name, abi, chain)
                for name, abi in self.retrieve_sub_config('contracts', chain)}

    def __bind_child_contracts(self):
        self.arbiter_staking.bind(
            address=self.bounty_registry.contract.functions.staking().call(), persistent=True
        )

    @classmethod
    def from_config_file(cls, name, filename):
        chain = cls.get_chain_details_from_file(filename)
        chain['name'] = name
        chain['contracts'] = cls.get_contracts_from_path(filename)
        return cls(chain)

    @classmethod
    def get_chain_details_from_file(cls, filename: str) -> Dict[str, Any]:
        with open(filename, 'r') as f:
            return yaml.safe_load(f)

    @classmethod
    def get_contracts_from_path(cls, path) -> Dict[str, Any]:
        contracts_dir = os.path.join(os.path.dirname(path), 'contracts')
        return cls.find_contracts_in_directory(contracts_dir)

    @classmethod
    def find_contracts_in_directory(cls, directory) -> Dict[str, Any]:
        for root, dirs, files in os.walk(directory):
            return {name: abi for name, abi in  cls.get_contracts_from_files(root, files)}

    @classmethod
    def get_contracts_from_files(cls, root, files) -> List[Tuple[str, Dict[str, Any]]]:
        return [cls.get_contract_from_filename(os.path.join(root, f)) for f in files]

    @classmethod
    def get_contract_from_filename(cls, filename) -> Tuple[str, Dict[str, Any]]:
        return cls.get_contract_name_from_filename(os.path.basename(filename)), cls.read_contract_from_file(filename)

    @classmethod
    def get_contract_name_from_filename(cls, filename):
        return os.path.splitext(filename)[0]

    @classmethod
    def read_contract_from_file(cls, filename) -> Dict[str, Any]:
        with open(filename, 'r') as f:
            return json.load(f)

    @classmethod
    def from_consul(cls, consul_client: Consul, name: str, community_key: str):
        chain = cls.fetch_config_from_consul(consul_client, name, community_key)
        chain['contracts'] = cls.fetch_contracts_from_consul(consul_client, community_key)
        return cls(chain)

    @classmethod
    def fetch_config_from_consul(cls, consul_client: Consul, name: str, key: str) -> Dict[str, Any]:
        config = ChainConfig.fetch_from_consul_or_wait(consul_client, f'{key}/{name}chain').get('Value')
        if config is None:
            raise ValueError(f'Invalid chain config for chain {name}')

        return json.loads(config.decode('utf-8'))

    @classmethod
    def fetch_contracts_from_consul(cls, consul_client: Consul, key: str) -> Dict[str, Any]:
        contracts: Dict[str, Any] = {}
        while True:
            contracts.update(cls.find_contracts_in_consul(consul_client, key))
            if cls.does_include_all_contracts(contracts):
                break

            logger.info('Key present but not all contracts deployed, retrying...')
            time.sleep(1)
        return contracts

    @classmethod
    def find_contracts_in_consul(cls, consul_client: Consul, key: str) -> Dict[str, Any]:
        contracts: Dict[str, Any] = {}
        for name, abi in cls.fetch_contract_parts_from_consul(consul_client, key):
            contracts[name] = abi
        return contracts

    @classmethod
    def fetch_contract_parts_from_consul(cls, consul_client: Consul, key: str):
        return [cls.parse_kv_pair(kv_pair) for kv_pair in cls.fetch_filtered_contract_kv_pairs(consul_client, key)]

    @classmethod
    def fetch_filtered_contract_kv_pairs(cls, consul_client: Consul, key: str):
        filter_k = cls.build_consul_key_filter(key)
        return [x for x in ChainConfig.fetch_from_consul_or_wait(consul_client, key, recurse=True)
                if x.get('Key') not in filter_k]

    @classmethod
    def build_consul_key_filter(cls, key) -> Set[str]:
        return {key + x for x in ('homechain', 'sidechain', 'config')}

    @staticmethod
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

    @classmethod
    def parse_kv_pair(cls, kv_pair) -> Tuple[str, Dict[str, Any]]:
        return cls.get_name_from_keypair(kv_pair), cls.get_abi_from_keypair(kv_pair)

    @classmethod
    def get_abi_from_keypair(cls, kv_pair) -> Dict[str, Any]:
        return json.loads(kv_pair.get('Value').decode('utf-8'))

    @classmethod
    def get_name_from_keypair(cls, kv_pair) -> str:
        return kv_pair.get('Key').rsplit('/', 1)[-1]

    @classmethod
    def does_include_all_contracts(cls, contracts: Dict[str, Any]) -> bool:
        return all([c in contracts for c in EXPECTED_CONTRACTS])

    @staticmethod
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

    def __validate(self):
        self.__validate_chain_id()
        self.__validate_contracts()

    def __validate_chain_id(self):
        if self.chain_id != int(self.w3.version.network):
            raise ValueError(
                'Chain ID mismatch, expected %s got %s', self.chain_id, int(self.w3.version.network)
            )

    def __validate_contracts(self):
        self.__validate_nectar_token()
        self.__validate_bounty_contracts()
        self.__validate_erc20_relay()
        self.__validate_offer_contracts()

    def __validate_nectar_token(self):
        if not self.nectar_token or not self.nectar_token.contract:
            raise ValueError('Invalid NectarToken contract or address')

    def __validate_bounty_contracts(self):
        self.__validate_bounty_registry()
        self.__validate_arbiter_staking()

    def __validate_bounty_registry(self):
        if not self.bounty_registry or not self.bounty_registry.contract:
            raise ValueError('Invalid BountyRegistry contract or address')

    def __validate_erc20_relay(self):
        if not self.erc20_relay or not self.erc20_relay.contract:
            raise ValueError('Invalid ERC20Relay contract or address')

    def __validate_arbiter_staking(self):
        # Child contracts not bound yet, but should be defined
        if not self.arbiter_staking:
            raise ValueError('Invalid ArbiterStaking contract')

    def __validate_offer_contracts(self):
        # Offer contracts only live on homechain
        if self.name == 'home':
            self.__validate_offer_registry()
            self.__validate_offer_multisig()

    def __validate_offer_registry(self):
        if not self.offer_registry or not self.offer_registry.contract:
            raise ValueError('Invalid OfferRegistry contract or address')

    def __validate_offer_multisig(self):
        if not self.offer_multisig:
            raise ValueError('Invalid OfferMultiSig contract')


class ConsulConfig(DictConfig):
    uri: str
    token: Optional[str]

    def __init__(self, consul: Dict[str, Any]):
        self.populate(consul)

    def populate(self, consul: Dict[str, Any]):
        self.populate_uri(consul)
        self.populate_token(consul)

    def populate_uri(self, consul: Dict[str, Any]):
        self.uri = self.retrieve_value('uri', consul)

    def populate_token(self, consul: Dict[str, Any]):
        try:
            self.token = self.retrieve_value('token', consul)
        except MissingConfigValueError:
            self.token = None


class DebugConfig(DictConfig):
    profiler_enabled: bool

    def __init__(self, profiler: Dict[str, Any]):
        self.populate_profile_enabled(profiler)

    def populate_profile_enabled(self, profiler: Dict[str, Any]):
        return self.retrieve_value('profiler_enabled', profiler)


class EthConfig(DictConfig):
    trace_transaction: bool

    def __init__(self, eth: Dict[str, Any]):
        self.populate_trace_transaction(eth)

    def populate_trace_transaction(self, eth: Dict[str, Any]):
        return self.retrieve_value('trace_transaction', eth)


class WebsocketConfig(DictConfig):
    enabled: bool

    def __init__(self, websocket: Dict[str, Any]):
        self.populate_enabled(websocket)

    def populate_enabled(self, websocket):
        try:
            self.enabled = self.retrieve_value('enabled', websocket)
        except MissingConfigValueError:
            self.enabled = not os.environ.get('DISABLE_WEBSOCKETS', False)


class Config(DictConfig):
    auth: AuthConfig
    community: str
    status: Status
    consul: ConsulConfig
    artifact: ArtifactConfig
    redis: Optional[Redis]
    chains: Dict[str, ChainConfig]
    websocket: WebsocketConfig
    debug: DebugConfig
    eth: EthConfig

    # Intentional class variable
    session = FuturesSession()

    def __init__(self, config: Dict[str, Any]):
        self.populate(config)
        self.status = Status(self.community)
        self.status.register_services(self.__create_services())
        self.__validate()

    @classmethod
    def auto(cls):
        return cls.from_config_file_search()

    @classmethod
    def from_config_file_search(cls):
        for location in CONFIG_LOCATIONS:
            location = os.path.abspath(os.path.expanduser(location))
            filename = os.path.join(location, 'polyswarmd.yml')
            if os.path.isfile(filename):
                return cls.create_from_file(filename)

        raise OSError('Config file not found')

    @classmethod
    def create_from_file(cls, path):
        with open(path, 'r') as f:
            return cls(yaml.safe_load(f))

    def populate(self, loaded: Dict[str, Any]):
        self.populate_community(loaded)
        self.populate_redis(loaded)
        self.load_sub_configs(loaded)

    def load_sub_configs(self, loaded: Dict[str, Any]):
        self.load_artifact(loaded)
        self.load_auth(loaded)
        self.load_debug(loaded)
        self.load_eth(loaded)
        self.load_websocket(loaded)
        self.load_chains_from_consul(loaded)

    def populate_community(self, loaded: Dict[str, Any]):
        self.community = self.retrieve_value("community", loaded)

    def populate_redis(self, loaded: Dict[str, Any]):
        try:
            redis_uri = self.retrieve_value('redis_uri', loaded)
            self.redis = redis.Redis.from_url(redis_uri)
        except MissingConfigValueError:
            pass

    def load_artifact(self, loaded: Dict[str, Any]):
        artifact = self.retrieve_value('artifact', loaded)
        self.artifact = ArtifactConfig(artifact)

    def load_eth(self, loaded: Dict[str, Any]):
        self.eth = EthConfig(self.retrieve_sub_config('eth', loaded))

    def load_auth(self, loaded: Dict[str, Any]):
        self.auth = AuthConfig(self.retrieve_sub_config('auth', loaded))

    def load_debug(self, loaded: Dict[str, Any]):
        self.debug = DebugConfig(self.retrieve_sub_config('debug', loaded))

    def load_websocket(self, loaded: Dict[str, Any]):
        self.websocket = WebsocketConfig(self.retrieve_sub_config('websocket', loaded))

    def load_chains_from_consul(self, loaded: Dict[str, Any]):
        consul_client = self.build_consul_client(loaded)
        self.chains = {
            'home': ChainConfig.from_consul(consul_client, 'home', f'chain/{self.community}'),
            'side': ChainConfig.from_consul(consul_client, 'side', f'chain/{self.community}')
        }

    def build_consul_client(self, loaded: Dict[str, Any]) -> Consul:
        self.load_consul(loaded)
        u = urlparse(self.consul.uri)
        return Consul(host=u.hostname, port=u.port, scheme=u.scheme, token=self.consul.token)

    def load_consul(self, loaded: Dict[str, Any]):
        self.consul = ConsulConfig(self.retrieve_sub_config('consul', loaded))
        ConsulService(self.consul.uri, self.session).wait_until_live()

    def __create_services(self):
        services = [*self.__create_ethereum_services(), self.__create_artifact_service()]
        if self.auth.uri:
            services.append(self.__create_auth_services())
        return services

    def __create_artifact_service(self):
        return ArtifactServices(self.artifact.client, self.session)

    def __create_ethereum_services(self):
        return [EthereumService(name, chain, self.session) for name, chain in self.chains.items()]

    def __create_auth_services(self):
        return AuthService(self.auth.uri, self.session)

    def __validate(self):
        self.__validate_community()
        self.__validate_services()
        self.__validate_artifacts()

    def __validate_community(self):
        if not self.community:
            raise ValueError('No community specified')

    def __validate_services(self):
        for service in self.status.services:
            self.__validate_service(service)

    @staticmethod
    def __validate_service(service):
        try:
            service.test_reachable()
        except HTTPError:
            raise ValueError(f'{service.name} not reachable, is correct URI specified?')

    def __validate_artifacts(self):
        self.__validate_artifact_limit()

    def __validate_artifact_limit(self):
        if self.artifact.limit < 1 or self.artifact.limit > 256:
            raise ValueError(
                'Artifact limit must be greater than 0 and cannot exceed contract limit of 256'
            )

    def __validate_artifact_fallback_size(self):
        if self.artifact.fallback_max_size < 1:
            raise ValueError('Fall back max artifact size must be above 0')
