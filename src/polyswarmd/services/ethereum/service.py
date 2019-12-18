from requests import HTTPError
from requests_futures.sessions import FuturesSession
from typing import Any, Dict

from polyswarmd.config import ChainConfig
from polyswarmd.services.service import Service, DEFAULT_FAILED_STATE


class EthereumService(Service):
    """Service declaration for Ethereum"""
    chain: ChainConfig
    session: FuturesSession
    uri: str

    def __init__(self, session, chain):
        super().__init__(chain.name)
        self.chain = chain
        self.session = session

    def get_reachable_and_chain_state(self) -> Dict[str, Any]:
        return {'reachable': True, 'syncing': self.is_syncing(), 'block': self.get_block()}

    def test_reachable(self):
        future = self.session.post(self.chain.eth_uri, headers={'Content-Type': 'application/json'})
        response = future.result()
        response.raise_for_status()

    def is_syncing(self) -> bool:
        return self.chain.w3.eth.syncing is not False

    def get_block(self) -> int:
        return self.chain.w3.eth.blockNumber

    def get_service_state(self) -> Dict[str, Any]:
        try:
            self.test_reachable()
            return self.get_reachable_and_chain_state()
        except HTTPError:
            return DEFAULT_FAILED_STATE
