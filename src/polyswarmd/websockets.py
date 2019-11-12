import json
import time

import jsonschema
from flask_sockets import Sockets
from geventwebsocket import WebSocketError
from jsonschema.exceptions import ValidationError
from requests.exceptions import ConnectionError

import gevent
from gevent.queue import Empty, Queue
from polyswarmd.chains import chain
from polyswarmd.filter_manager import (ClosedAgreement, FilterManager,
                                       SettleStateChanged, StartedSettle)
from polyswarmd.utils import (channel_to_dict, g, logging, state_to_dict, uuid)

logger = logging.getLogger(__name__)


class WebsocketMessage(object):
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    _ws_event = 'websocket'
    __slots__ = ('data')

    @property
    def event(self):
        return self._ws_event

    def __init__(self, data={}):
        self.data = data

    def as_dict(self):
        "`as_dict' should return an object representing the websocket message that the client will consume"
        return {'event': self.event, 'data': self.data}

    def __str__(self):
        return json.dumps(self.as_dict())


class WebSocket:
    """
    Wrapper around a WebSocket that has a queue of messages that can be sent from another greenlet.
    """
    def __init__(self, ws):
        """
        Create a wrapper around a WebSocket with a guid to easily identify it, and a queue of messages to send
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
        return isinstance(other, WebSocket) and \
               other.guid == self.guid


class Connected(WebsocketMessage):
    _ws_event = 'connected'


def init_websockets(app):
    sockets = Sockets(app)
    start_time = time.time()
    message_sockets = dict()

    @sockets.route('/events')
    @chain(account_required=False)
    def events(ws):
        rpc = g.chain.rpc
        ws.send(Connected({'start_time': str(start_time)}))

        wrapper = WebSocket(ws)

        rpc.register(wrapper)

        while not ws.closed:
            try:
                # Try to read a message off the queue, and then send over the websocket.
                msg = wrapper.queue.get(block=False)
                ws.send(msg)
            except Empty:
                # Anytime there are no new messages to send, check that the websocket is still connected with ws.receive
                with gevent.Timeout(.5, False):
                    logger.debug('Checking %s against timeout', wrapper)
                    # This raises WebSocketError if socket is closed, and does not block if there are no messages
                    ws.receive()
            except WebSocketError as e:
                logger.error('Websocket %s closed %s', wrapper, e)
                rpc.unregister(wrapper)
                return

        rpc.unregister(wrapper)

    @sockets.route('/events/<uuid:guid>')
    @chain(chain_name='home', account_required=False)
    def channel_events(ws, guid):
        offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
        msig_address = offer_channel['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        fmanager = FilterManager()

        while not ws.closed:
            try:
                if not fmanager.has_registered():
                    for evt in [ClosedAgreement, StartedSettle, SettleStateChanged]:
                        fmanager.register(offer_msig.eventFilter(evt.filter_id), evt)

                for event in fmanager.new_ws_events():
                    ws.send(event)

                gevent.sleep(1)
            except WebSocketError:
                logger.info('Websocket connection closed, exiting loop')
                break
            except ConnectionError:
                logger.exception('ConnectionError in offer /events (is geth down?)')
                fmanager.unregister_all()
                continue
            except Exception:
                logger.exception('Exception in /events, resetting filters')
                fmanager.unregister_all()
                continue

    # for receiving messages about offers that might need to be signed
    @sockets.route('/messages/<uuid:guid>')
    @chain(chain_name='home', account_required=False)
    def messages(ws, guid):

        if guid not in message_sockets:
            message_sockets[guid] = [ws]
        else:
            message_sockets[guid].append(ws)

        while not ws.closed:
            try:
                msg = ws.receive()

                if not msg:
                    break

                schema = {
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
                }

                body = json.loads(msg)

                try:
                    jsonschema.validate(body, schema)
                except ValidationError:
                    logger.exception('Invalid JSON')

                state_dict = state_to_dict(body['state'])
                state_dict['guid'] = guid.int
                ret = {'type': body['type'], 'raw_state': body['state'], 'state': state_dict}

                if 'r' in body:
                    ret['r'] = body['r']

                if 'v' in body:
                    ret['v'] = body['v']

                if 's' in body:
                    ret['s'] = body['s']

                if 'artifact' in body:
                    ret['artifact'] = body['artifact']

                if body['type'] != 'accept' and body['type'] != 'payout':
                    # delete zero verdict
                    if 'mask' in ret['state']:
                        del ret['state']['mask']
                        del ret['state']['verdicts']

                for message_websocket in message_sockets[guid]:
                    if not message_websocket.closed:
                        message_websocket.send(json.dumps(ret))

                gevent.sleep(1)
            except WebSocketError:
                logger.info('Websocket connection closed, exiting loop')
                break
            except Exception:
                logger.exception('Exception in /events')
                continue
