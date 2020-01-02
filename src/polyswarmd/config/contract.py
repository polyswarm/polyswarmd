import logging
from typing import Any, Dict

from web3 import Web3
from web3.exceptions import MismatchedABI

from polyswarmd.utils import camel_case_to_snake_case


logger = logging.getLogger(__name__)

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

    @staticmethod
    def from_json(w3: Web3, name: str, contract: Dict[str, Any], config: Dict[str, Any]):
        if 'abi' not in contract:
            return None

        abi = contract.get('abi')

        # XXX: OfferMultiSig doesn't follow this convention, but we don't bind that now anyway
        address = config.get(camel_case_to_snake_case(name) + '_address')

        return Contract(w3, name, abi, address)
