import importlib
import logging
import os
import sys
from typing import Dict, Any, Optional, ClassVar, List
from urllib.parse import urlparse

import jsonschema
import yaml

from consul import Consul as ConsulClient
from jsonschema import ValidationError
from redis import Redis as RedisClient
from requests import HTTPError
from requests_futures.sessions import FuturesSession

from polyswarmd.config.contract import Chain, ConsulChain, FileChain
from polyswarmd.config.schema import POLYSWARMD_CONFIG_SCHEMA
from polyswarmd.exceptions import MissingConfigValueError
from polyswarmd.services.artifact import AbstractArtifactServiceClient, ArtifactServices
from polyswarmd.services.auth import AuthService
from polyswarmd.services.consul import ConsulService
from polyswarmd.services.ethereum import EthereumService
from polyswarmd.config.status import Status
from polyswarmd.config.config import Config

logger = logging.getLogger(__name__)

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']
DEFAULT_FALLBACK_SIZE = 10 * 1024 * 1024


class ClassModuleLoader:
    module_name: str
    class_name: str

    def __init__(self, module_name: str, class_name: str):
        self.module_name = module_name
        self.class_name = class_name

    def load(self):
        client_module = importlib.import_module(self.module_name)
        return getattr(client_module, self.class_name)


class Library(Config):
    module: str
    class_name: str
    args: List[Any]
    client: AbstractArtifactServiceClient

    def finish(self):
        if not hasattr(self, 'module'):
            MissingConfigValueError('No module specified for artifact service client')

        if not hasattr(self, 'class_name'):
            MissingConfigValueError('No class name specified for artifact service client')

        if not hasattr(self, 'args'):
            self.args = []

        self.client = ClassModuleLoader(self.module, self.class_name).load()(*self.args)


class Artifact(Config):
    library: Library
    limit: int
    fallback_max_size: int
    max_size: int

    def finish(self):
        if not hasattr(self, 'limit'):
            self.limit = 256

        if self.limit < 1 or self.limit > 256:
            raise ValueError(
                'Artifact limit must be greater than 0 and cannot exceed contract limit of 256'
            )

        if not hasattr(self, 'max_size'):
            self.max_size = int(os.environ.get('MAX_ARTIFACT_SIZE', DEFAULT_FALLBACK_SIZE))

        if not hasattr(self, 'fallback_max_size'):
            self.fallback_max_size = DEFAULT_FALLBACK_SIZE

        if self.fallback_max_size < 1:
            raise ValueError('Fall back max artifact size must be above 0')

        if not hasattr(self, 'library'):
            MissingConfigValueError('Failed to load artifact services client')

    @property
    def client(self):
        return self.library.client


class Auth(Config):
    uri: Optional[str]

    def finish(self):
        if not hasattr(self, 'uri'):
            self.uri = None

    @property
    def require_api_key(self):
        return self.uri is not None


class Consul(Config):
    uri: str
    token: Optional[str]
    client: ConsulClient

    def finish(self):
        if not hasattr(self, 'uri'):
            raise MissingConfigValueError('Missing consul URI')

        if not hasattr(self, 'token'):
            self.token = None

        ConsulService(self.uri, FuturesSession()).wait_until_live()
        u = urlparse(self.uri)
        self.client = ConsulClient(host=u.hostname, port=u.port, scheme=u.scheme, token=self.token)


class Eth(Config):
    trace_transactions: bool
    consul: Optional[Consul]
    directory: Optional[str]

    def finish(self):
        if not hasattr(self, 'trace_transactions') or self.trace_transactions is None:
            self.trace_transactions = False

        if not hasattr(self, 'consul'):
            self.consul = None

        if not hasattr(self, 'directory'):
            self.directory = None

        if self.consul is not None and self.directory is not None:
            raise ValueError('Cannot have both filename and consul values')
        elif self.consul is None and self.directory is None:
            raise MissingConfigValueError('Must specify either consul or filename')

    def get_chains(self, community: str) -> Dict[str, Chain]:
        if self.consul is not None:
            return {network: ConsulChain.from_consul(self.consul.client, network, f'chain/{community}')
                    for network in ['home', 'side']}
        else:
            return {chain: FileChain.from_config_file(chain, os.path.join(self.directory, f'{chain}chain.json'))
                    for chain in ['home', 'side']}


class Profiler(Config):
    enabled: bool
    db_uri: Optional[str]

    def finish(self):
        if not hasattr(self, 'enabled'):
            self.enabled = False
            self.db_uri = None

        if not hasattr(self, 'db_uri'):
            self.db_uri = None

        if self.enabled and self.db_uri is None:
            raise ValueError('Profiler enabled, but no db uri set')


class Websocket(Config):
    enabled: bool

    def finish(self):
        if not hasattr(self, 'enabled') or self.enabled is None:
            if os.environ.get('DISABLE_WEBSOCKETS') is not None:
                self.enabled = False
                logger.warning('"DISABLE_WEBSOCKETS" environment variable is deprecated, please use configuration')


class Redis(Config):
    client: Optional[RedisClient]
    uri: str

    def finish(self):
        if hasattr(self, 'uri'):
            self.client = RedisClient.from_url(self.uri)
        else:
            self.client = None


class PolySwarmd(Config):
    session: FuturesSession
    status: Status
    artifact: Artifact
    auth: Auth
    chains: Dict[str, Chain]
    community: str
    eth: Eth
    profiler: Profiler
    redis: Redis
    websocket: Websocket

    def __init__(self, config: Dict[str, Any]):
        self.session = FuturesSession()
        try:
            jsonschema.validate(config, POLYSWARMD_CONFIG_SCHEMA)
        except ValidationError:
            raise MissingConfigValueError('Invalid Config')
        super().__init__(config, module=sys.modules[__name__])

    @staticmethod
    def auto():
        return PolySwarmd.from_config_file_search()

    @staticmethod
    def from_config_file_search():
        for location in CONFIG_LOCATIONS:
            location = os.path.abspath(os.path.expanduser(location))
            filename = os.path.join(location, 'polyswarmd.yml')
            if os.path.isfile(filename):
                return PolySwarmd.create_from_file(filename)

        raise OSError('Config file not found')

    @staticmethod
    def create_from_file(path):
        with open(path, 'r') as f:
            return PolySwarmd(yaml.safe_load(f))

    def finish(self):
        self.check_community()
        self.fill_default_sub_configs()
        self.load_chains()
        self.setup_status()

    def check_community(self):
        if not hasattr(self, 'community'):
            raise MissingConfigValueError('Missing community')

    def fill_default_sub_configs(self):
        sub_configs = [('artifact', Artifact), ('auth', Auth), ('eth', Eth), ('profiler', Profiler), ('redis', Redis),
                       ('websocket', Websocket)]
        for attribute, sub_config in sub_configs:
            self.create_default_sub_config_if_missing(attribute, sub_config)

    def create_default_sub_config_if_missing(self, attribute: str, sub_config: ClassVar[Config]):
        if not hasattr(self, attribute):
            setattr(self, attribute, sub_config({}))

    def load_chains(self):
        self.chains = self.eth.get_chains(self.community)

    def setup_status(self):
        self.status = Status(self.community)
        self.status.register_services(self.__create_services())
        self.validate_services()

    def __create_services(self):
        services = [*self.create_ethereum_services(), self.create_artifact_service()]
        if self.auth.uri:
            services.append(self.create_auth_services())
        return services

    def create_artifact_service(self):
        return ArtifactServices(self.artifact.client, self.session)

    def create_ethereum_services(self):
        return [EthereumService(name, chain, self.session) for name, chain in self.chains.items()]

    def create_auth_services(self):
        return AuthService(self.auth.uri, self.session)

    def validate_services(self):
        for service in self.status.services:
            self.validate_service(service)

    @staticmethod
    def validate_service(service):
        try:
            service.test_reachable()
        except HTTPError:
            raise ValueError(f'{service.name} not reachable, is correct URI specified?')
