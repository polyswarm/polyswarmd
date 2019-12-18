from requests_futures.sessions import FuturesSession

from polyswarmd.services.service import Service


class AuthService(Service):
    """Service declaration for Ethereum"""
    session: FuturesSession
    base_uri: str

    def __init__(self, session, base_uri):
        super().__init__('auth')
        self.base_uri = base_uri
        self.session = session

    @property
    def uri(self) -> str:
        return f'{self.base_uri}/communities/public'

    def test_reachable(self):
        future = self.session.post(self.uri)
        response = future.result()
        response.raise_for_status()
