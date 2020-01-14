import json
import logging
import os
import time
from typing import Any, Dict, List, Set, Tuple

import jsonschema
import yaml
from consul import Timeout
from jsonschema import ValidationError

from polyswarmd.config.config import Config
from web3 import Web3, HTTPProvider
from web3.exceptions import MismatchedABI
from web3.middleware import geth_poa_middleware

from polyswarmd.config.schema import CHAIN_CONFIG_SCHEMA
from polyswarmd.exceptions import MissingConfigValueError
from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.utils import camel_case_to_snake_case, IN_TESTENV

logger = logging.getLogger(__name__)
EXPECTED_CONTRACTS = ['NectarToken', 'BountyRegistry', 'ArbiterStaking', 'ERC20Relay', 'OfferRegistry', 'OfferMultiSig']

# Allow interfacing with contract versions in this range
SUPPORTED_CONTRACT_VERSIONS = {
    'ArbiterStaking': ((1, 2, 0), (1, 3, 0)),
    'BountyRegistry': ((1, 6, 0), (1, 7, 0)),
    'ERC20Relay': ((1, 2, 0), (1, 4, 0)),
    'OfferRegistry': ((1, 2, 0), (1, 3, 0)),
}


class Contract(object):

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
        if IN_TESTENV:
            logger.info("We are inside a test environment, skipping contract VERSION check")
        elif supported_versions is not None and address != ZERO_ADDRESS:
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

    @staticmethod
    def from_json(w3: Web3, name: str, contract: Dict[str, Any], config: Dict[str, Any]):
        if 'abi' not in contract:
            return None

        abi = contract.get('abi')

        # XXX: OfferMultiSig doesn't follow this convention, but we don't bind that now anyway
        address = config.get(camel_case_to_snake_case(name) + '_address')

        return Contract(w3, name, abi, address)


class Chain(Config):
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
    offer_multi_sig: Contract
    rpc: EthereumRpc

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        try:
            jsonschema.validate(config, CHAIN_CONFIG_SCHEMA)
        except ValidationError:
            raise MissingConfigValueError('Invalid config')

        super().__init__(config)

    def populate(self, config: Dict[str, Any], module):
        self.eth_uri = config.get('eth_uri', None)
        if self.eth_uri is None:
            raise MissingConfigValueError('Missing eth_uri')

        self.setup_web3(self.eth_uri)
        contract_abis = config.get('contracts')
        del config['contracts']
        contracts = self.create_bound_contract_dicts(contract_abis, config)
        config.update(contracts)
        super().populate(config, module)

    def finish(self):
        if not IN_TESTENV:
            self.__bind_child_contracts()
            self.__validate()
        self.setup_rpc()

    def setup_web3(self, eth_uri: str):
        self.w3 = Web3(HTTPProvider(eth_uri))
        self.w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    def setup_rpc(self):
        self.rpc = EthereumRpc(self)

    def create_bound_contract_dicts(self, contracts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Contract]:
        return {camel_case_to_snake_case(name): self.create_contract(name, abi, config) for name, abi in contracts.items()}

    def create_contract(self, name, abi, config: Dict[str, Any]) -> Contract:
        return Contract.from_json(self.w3, name, abi, config)

    def __bind_child_contracts(self):
        self.arbiter_staking.bind(address=self.bounty_registry.contract.functions.staking().call(), persistent=True)

    @staticmethod
    def does_include_all_contracts(contracts: Dict[str, Any]) -> bool:
        return all([c in contracts for c in EXPECTED_CONTRACTS])

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
            self.__validate_offer_multi_sig()

    def __validate_offer_registry(self):
        if not self.offer_registry or not self.offer_registry.contract:
            raise ValueError('Invalid OfferRegistry contract or address')

    def __validate_offer_multi_sig(self):
        if not self.offer_multi_sig:
            raise ValueError('Invalid OfferMultiSig contract')


class ConsulChain(Chain):
    @classmethod
    def from_consul(cls, consul_client, name: str, community_key: str):
        chain = cls.fetch_config(consul_client, name, community_key)
        chain['contracts'] = cls.fetch_contracts(consul_client, community_key)
        return cls(name, chain)

    @classmethod
    def fetch_config(cls, consul_client, name: str, key: str) -> Dict[str, Any]:
        config = cls.fetch_from_consul_or_wait(consul_client, f'{key}/{name}chain').get('Value')
        if config is None:
            raise ValueError(f'Invalid chain config for chain {name}')

        return json.loads(config.decode('utf-8'))

    @classmethod
    def fetch_contracts(cls, consul_client, key: str) -> Dict[str, Any]:
        contracts: Dict[str, Any] = {}
        while True:
            contracts.update(cls.find_contracts(consul_client, key))
            if cls.does_include_all_contracts(contracts):
                break

            logger.info('Key present but not all contracts deployed, retrying...')
            time.sleep(1)
        return contracts

    @classmethod
    def find_contracts(cls, consul_client, key: str) -> Dict[str, Any]:
        return {name: abi for name, abi in cls.fetch_contract_parts(consul_client, key)}

    @classmethod
    def fetch_contract_parts(cls, consul_client, key: str) -> List[Tuple[str, Dict[str, Any]]]:
        return [cls.parse_kv_pair(kv_pair) for kv_pair in cls.fetch_contract_kv_pairs(consul_client, key)]

    @classmethod
    def parse_kv_pair(cls, kv_pair) -> Tuple[str, Dict[str, Any]]:
        return cls.get_name(kv_pair), cls.get_abi(kv_pair)

    @classmethod
    def get_abi(cls, kv_pair) -> Dict[str, Any]:
        return json.loads(kv_pair.get('Value').decode('utf-8'))

    @classmethod
    def get_name(cls, kv_pair) -> str:
        return kv_pair.get('Key').rsplit('/', 1)[-1]

    @classmethod
    def fetch_contract_kv_pairs(cls, consul_client, key: str) -> List[Any]:
        filter_ = cls.contract_filter(key)
        return [x for x in cls.fetch_from_consul_or_wait(consul_client, key, recurse=True)
                if x.get('Key') not in filter_]

    @classmethod
    def contract_filter(cls, key) -> Set[str]:
        return {f'{key}/{x}' for x in ('homechain', 'sidechain', 'config')}

    @staticmethod
    def fetch_from_consul_or_wait(client, key, recurse=False, index=0) -> Any:
        while True:
            try:
                index, data = client.kv.get(key, recurse=recurse, index=index, wait='2m')
                if data is not None:
                    return data
            except Timeout:
                logger.info('Consul up but key %s not available, retrying...', key)
                continue

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


class FileChain(Chain):
    @classmethod
    def from_config_file(cls, name, filename):
        chain = cls.load_chain_details(filename)
        chain['contracts'] = cls.load_contracts(filename)
        return cls(name, chain)

    @classmethod
    def load_chain_details(cls, filename: str) -> Dict[str, Any]:
        with open(filename, 'r') as f:
            return yaml.safe_load(f)

    @classmethod
    def load_contracts(cls, path) -> Dict[str, Any]:
        contracts_dir = os.path.dirname(path)
        return cls.load_contracts_from_dir(contracts_dir)

    @classmethod
    def load_contracts_from_dir(cls, directory) -> Dict[str, Any]:
        return {
            name: abi
            for root, dirs, files in os.walk(directory)
            for name, abi in cls.load_contract_files(root, files)
        }

    @classmethod
    def load_contract_files(cls, root: str, files: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
        filter_ = cls.contract_filter()
        return [cls.load_contract(os.path.join(root, f)) for f in files if f not in filter_]

    @classmethod
    def contract_filter(cls) -> Set[str]:
        return {f'{x}.json' for x in ('homechain', 'sidechain', 'config')}

    @classmethod
    def load_contract(cls, filename: str) -> Tuple[str, Dict[str, Any]]:
        return cls.get_name(os.path.basename(filename)), cls.get_abi(filename)

    @classmethod
    def get_name(cls, filename: str):
        return os.path.splitext(filename)[0]

    @classmethod
    def get_abi(cls, filename: str) -> Dict[str, Any]:
        with open(filename, 'r') as f:
            return json.load(f)
