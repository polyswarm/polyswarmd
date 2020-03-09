import uuid
import fastjsonschema

from gevent.queue import Queue


class WebSocket:
    """
    Wrapper around a WebSocket that has a queue of messages that can be sent from another greenlet.
    """

    def __init__(self, ws):
        """
        Create a wrapper around a WebSocket with a guid to easily identify it, and a queue of
        messages to send
        :param ws: gevent WebSocket to wrap
        """
        self.guid = uuid.uuid4()
        self.ws = ws
        self.queue = Queue()

    def send(self, message):
        """
        Add message to the queue of messages to be sent
        :param message: json blob to be sent over the WebSocket
        """
        self.queue.put(message)

    def __repr__(self):
        return f'<Websocket UUID={str(self.guid)}>'

    def __eq__(self, other):
        return isinstance(other, WebSocket) and other.guid == self.guid


_messages_schema = fastjsonschema.compile({
    'type': 'object',
    'properties': {
        'type': {
            'type': 'string',
        },
        'from_socket': {
            'type': 'string',
        },
        'to_socket': {
            'type': 'string',
        },
        'state': {
            'type': 'string',
        },
        'artifact': {
            'type': 'string',
        },
        'r': {
            'type': 'string',
        },
        'v': {
            'type': 'integer',
        },
        's': {
            'type': 'string',
        }
    },
    'required': ['type', 'state'],
})
