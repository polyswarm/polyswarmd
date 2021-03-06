from polyswarmd.config.service import Service


class AuthService(Service):
    """Service declaration for Ethereum"""

    def __init__(self, base_uri, session):
        super().__init__('auth', AuthService.build_uri(base_uri), session)

    @staticmethod
    def build_uri(base_uri) -> str:
        return f'{base_uri}/communities/public'

    def connect_to_service(self):
        future = self.session.get(self.uri)
        response = future.result()
        response.raise_for_status()
