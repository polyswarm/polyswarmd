from polyswarmd.config.service import Service


class AuthService(Service):
    """Service declaration for Ethereum"""

    def __init__(self, session, base_uri):
        super().__init__('auth', AuthService.build_uri(base_uri), session)

    @staticmethod
    def build_uri(base_uri) -> str:
        return f'{base_uri}/communities/public'
