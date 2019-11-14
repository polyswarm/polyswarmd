import json
import time

import gevent
import jsonschema
from flask_sockets import Sockets
from gevent.queue import Empty, Queue
from geventwebsocket import WebSocketError
from jsonschema.exceptions import ValidationError
from polyswarmd.chains import chain
from polyswarmd.utils import channel_to_dict, g, logging, state_to_dict, uuid

from .messages import (ClosedAgreement, Connected, SettleStateChallenged,
                       StartedSettle)

logger = logging.getLogger(__name__)


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
        from polyswarmd.rpc import FilterManager
        offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
        msig_address = offer_channel['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        fmanager = FilterManager()
        for evt in [ClosedAgreement, StartedSettle, SettleStateChallenged]:
            fmanager.register(offer_msig.eventFilter(evt.filter_event), evt)

        def send(msg):
            if ws.closed:
                raise RuntimeError("WebSocket is closed")
            return ws.send(msg)

        fmanager.event_pool(ws.send).join()

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
