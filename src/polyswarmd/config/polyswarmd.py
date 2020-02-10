import dataclasses
import logging
import os
import warnings
import yaml

from requests_futures.sessions import FuturesSession
from typing import Dict, Optional

from polyswarmdconfig import Artifact, Auth, Config, Consul, Redis
from polyswarmd.config.contract import Chain, ConsulChain, FileChain
from polyswarmd.config.status import Status
from polyswarmd.services.artifact import ArtifactServices
from polyswarmd.services.auth import AuthService
from polyswarmd.services.ethereum import EthereumService
from polyswarmd.utils.utils import IN_TESTENV

logger = logging.getLogger(__name__)

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']
if IN_TESTENV:
    # XXX: This is a huge hack to work around the issue that you have to load a function to
    # monkeypatch it. Because __init__.py alone has enough to break tests, this is an
    # alternative way to signal that we shouldn't perform "ordinary" file loading
    CONFIG_LOCATIONS = ['tests/fixtures/config/polyswarmd/']

DEFAULT_FALLBACK_SIZE = 10 * 1024 * 1024


@dataclasses.dataclass
class Eth(Config):
    trace_transactions: bool = True
    consul: Optional[Consul] = None
    directory: Optional[str] = None

    def __post_init__(self):
        if self.consul is not None and self.directory is not None:
            raise ValueError('Cannot have both directory and consul values')
        elif self.consul is None and self.directory is None:
            raise MissingConfigValueError('Must specify either consul or directory')

    def get_chains(self, community: str) -> Dict[str, Chain]:
        if self.consul is not None:
            return {
                network: ConsulChain.from_consul(self.consul.client, network, f'chain/{community}')
                for network in ['home', 'side']
            }
        else:
            return {
                chain: FileChain.from_config_file(
                    chain, os.path.join(self.directory, f'{chain}chain.json')
                ) for chain in ['home', 'side']
            }


@dataclasses.dataclass
class Profiler(Config):
    enabled: bool = False
    db_uri: Optional[str] = None

    def __post_init__(self):
        if self.enabled and self.db_uri is None:
            raise ValueError('Profiler enabled, but no db uri set')


@dataclasses.dataclass
class Websocket(Config):
    enabled: bool = True

    def __post_init__(self):
        if self.enabled and os.environ.get('DISABLE_WEBSOCKETS'):
            self.enabled = False
            warnings.warn(
                '"DISABLE_WEBSOCKETS" environment variable is deprecated, please use POLYSWARMD_WEBSOCKET_ENABLED',
                DeprecationWarning)


@dataclasses.dataclass
class PolySwarmd(Config):
    artifact: Artifact
    community: str
    auth: Auth = dataclasses.field(default_factory=Auth)
    chains: Dict[str, Chain] = dataclasses.field(init=False)
    eth: Eth = dataclasses.field(default_factory=Eth)
    profiler: Profiler = dataclasses.field(default_factory=Profiler)
    redis: Redis = dataclasses.field(default_factory=Redis)
    status: Status = dataclasses.field(init=False)
    session: FuturesSession = dataclasses.field(init=False, default_factory=FuturesSession)
    websocket: Websocket = dataclasses.field(default_factory=Websocket)

    @staticmethod
    def auto():
        return PolySwarmd.from_config_file_search()

    @staticmethod
    def from_config_file_search():
        # Expect config in the environment
        for location in CONFIG_LOCATIONS:
            location = os.path.abspath(os.path.expanduser(location))
            filename = os.path.join(location, 'polyswarmd.yml')
            if os.path.isfile(filename):
                return PolySwarmd.create_from_file(filename)

        else:
            return PolySwarmd.from_dict_and_environment({})

    @staticmethod
    def create_from_file(path):
        with open(path, 'r') as f:
            return PolySwarmd.from_dict_and_environment(yaml.safe_load(f))

    def __post_init__(self):
        self.setup_chains()
        self.setup_status()

    def setup_chains(self):
        self.chains = self.eth.get_chains(self.community)

    def setup_status(self):
        self.status = Status(self.community)
        self.status.register_services(self.__create_services())

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
