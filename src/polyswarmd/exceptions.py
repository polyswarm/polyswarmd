class PolyswarmdException(Exception):

    def __init__(self, message=None):
        self.message = message


class WebsocketConnectionAbortedError(Exception):
    """Exception thrown when no clients exist to broadcast to"""

    def __init__(self, message=None):
        self.message = message


class MissingConfigValueError(PolyswarmdException):

    def __init__(self, key):
        super().__init__(f'Missing {key} from config file')
