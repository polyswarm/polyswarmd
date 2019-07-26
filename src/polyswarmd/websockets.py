import gevent
import json
import jsonschema
import time

from gevent.queue import Queue, Empty

from flask_sockets import Sockets
from gevent.lock import BoundedSemaphore
from geventwebsocket import WebSocketError
from jsonschema.exceptions import ValidationError
from requests.exceptions import ConnectionError
from polyswarmd.chains import chain
from polyswarmd.utils import *

logger = logging.getLogger(__name__)


class Websocket:
    def __init__(self, ws):
        self.guid = uuid.uuid4()
        self.ws = ws
        self.queue = Queue()

    def send(self, message):
        self.queue.put(message)

    def __repr__(self):
        return f'<Websocket UUID={str(self.guid)}>'

    def __eq__(self, other):
        return isinstance(other, Websocket) and \
               other.guid == self.guid


def init_websockets(app):
    sockets = Sockets(app)
    start_time = time.time()
    message_sockets = dict()

    @sockets.route('/events')
    @chain(account_required=False)
    def events(ws):
        rpc = g.chain.rpc
        ws.send(
            json.dumps({
                'event': 'connected',
                'data': {
                    'start_time': str(start_time),
                }
            }))

        wrapper = Websocket(ws)

        rpc.register(wrapper)

        while not ws.closed:
            try:
                msg = wrapper.queue.get(block=False)
                try:
                    ws.send(msg)
                except WebSocketError as e:
                    logger.error('Websocket %s closed %s', wrapper, e)
                    rpc.unregister(wrapper)
                    return
            except Empty:
                with gevent.Timeout(.5, False):
                    logger.debug('Checking %s against timeout', wrapper)
                    ws.receive()

        rpc.unregister(wrapper)

    @sockets.route('/events/<uuid:guid>')
    @chain(chain_name='home', account_required=False)
    def channel_events(ws, guid):
        offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
        msig_address = offer_channel['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)

        filters_initialized = False
        while not ws.closed:
            try:
                if not filters_initialized:
                    closed_agreement_filter = offer_msig.eventFilter('ClosedAgreement')
                    settle_started_filter = offer_msig.eventFilter('StartedSettle')
                    settle_challenged_filter = offer_msig.eventFilter('SettleStateChallenged')

                    filters_initialized = True

                for event in closed_agreement_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event': 'closed_agreement',
                            'data': new_cancel_agreement_event_to_dict(event.args),
                            'block_number': event.blockNumber,
                            'txhash': event.transactionHash.hex(),
                        }))

                for event in settle_started_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event': 'settle_started',
                            'data': new_settle_started_event(event.args),
                            'block_number': event.blockNumber,
                            'txhash': event.transactionHash.hex(),
                        }))

                for event in settle_challenged_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event': 'settle_challenged',
                            'data': new_settle_challenged_event(event.args),
                            'block_number': event.blockNumber,
                            'txhash': event.transactionHash.hex(),
                        }))

                gevent.sleep(1)
            except WebSocketError:
                logger.info('Websocket connection closed, exiting loop')
                break
            except ConnectionError:
                logger.exception('ConnectionError in offer /events (is geth down?)')
                filters_initialized = False
                continue
            except Exception:
                logger.exception('Exception in /events, resetting filters')
                filters_initialized = False
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
                ret = {
                    'type': body['type'],
                    'raw_state': body['state'],
                    'state': state_dict
                }

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
                        message_websocket.send(
                            json.dumps(ret))

                gevent.sleep(1)
            except WebSocketError:
                logger.info('Websocket connection closed, exiting loop')
                break
            except Exception:
                logger.exception('Exception in /events')
                continue
