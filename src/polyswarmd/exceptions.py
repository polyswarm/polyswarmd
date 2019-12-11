class PolyswarmdException(Exception):

    def __init__(self, message=None):
        self.message = message


class WebsocketConnectionAbortedError(Exception):
    """Exception thrown when no clients exist to broadcast to"""

    def __init__(self, message=None):
        self.message = message
