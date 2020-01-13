from typing import Any, Dict

from polyswarmd.config.service import Service


class EthereumService(Service):
    """Service for Ethereum"""

    def __init__(self, name, chain, session):
        self.chain = chain
        super().__init__(name, chain.eth_uri, session)

    def build_output(self, reachable) -> Dict[str, Any]:
        if reachable:
            return {'reachable': True, 'syncing': self.is_syncing(), 'block': self.get_block()}
        else:
            super().build_output(False)

    def connect_to_service(self):
        future = self.session.post(self.uri, headers={'Content-Type': 'application/json'})
        response = future.result()
        response.raise_for_status()

    def is_syncing(self) -> bool:
        return self.chain.w3.eth.syncing is not False

    def get_block(self) -> int:
        return self.chain.w3.eth.blockNumber