import gevent
import json
import jsonschema
import logging
import time

from jsonschema.exceptions import ValidationError
from flask import g
from flask_sockets import Sockets
from geventwebsocket import WebSocketError
from requests.exceptions import ConnectionError

from polyswarmd.chains import chain
from polyswarmd.utils import *

logger = logging.getLogger(__name__)


def init_websockets(app):
    sockets = Sockets(app)
    start_time = time.time()
    message_sockets = dict()

    @sockets.route('/events')
    @chain(account_required=False)
    def events(ws):
        ws.send(
            json.dumps({
                'event': 'connected',
                'data': {
                    'start_time': str(start_time),
                }
            }))

        filters_initialized = False
        latest_block = 0

        while not ws.closed:
            try:
                if not filters_initialized:
                    from_block = "latest" if latest_block == 0 else latest_block
                    block_filter = g.chain.w3.eth.filter(from_block)
                    fee_filter = g.chain.bounty_registry.contract.eventFilter('FeesUpdated', {'fromBlock': from_block})
                    window_filter = g.chain.bounty_registry.contract.eventFilter('WindowsUpdated',
                                                                                 {'fromBlock': from_block})
                    bounty_filter = g.chain.bounty_registry.contract.eventFilter('NewBounty', {'fromBlock': from_block})
                    assertion_filter = g.chain.bounty_registry.contract.eventFilter('NewAssertion',
                                                                                    {'fromBlock': from_block})
                    vote_filter = g.chain.bounty_registry.contract.eventFilter('NewVote', {'fromBlock': from_block})
                    quorum_filiter = g.chain.bounty_registry.contract.eventFilter('QuorumReached',
                                                                                  {'fromBlock': from_block})
                    settled_filter = g.chain.bounty_registry.contract.eventFilter('SettledBounty',
                                                                                  {'fromBlock': from_block})
                    reveal_filter = g.chain.bounty_registry.contract.eventFilter('RevealedAssertion',
                                                                                 {'fromBlock': from_block})
                    init_filter = None
                    if g.chain.offer_registry.contract is not None:
                        init_filter = g.chain.offer_registry.contract.eventFilter('InitializedChannel')

                    filters_initialized = True

                try:
                    temp_block = 0
                    for event in fee_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'fee_update',
                                'data': fee_update_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in window_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'window_update',
                                'data': window_update_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in bounty_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'bounty',
                                'data': new_bounty_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in assertion_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'assertion',
                                'data': new_assertion_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in reveal_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'reveal',
                                'data': revealed_assertion_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in vote_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'vote',
                                'data': new_vote_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in quorum_filiter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'quorum',
                                'data': new_quorum_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for event in settled_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'settled_bounty',
                                'data': settled_bounty_event_to_dict(event.args),
                                'block_number': event.blockNumber,
                                'txhash': event.transactionHash.hex(),
                            }))
                        temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    if init_filter is not None:
                        for event in init_filter.get_new_entries():
                            ws.send(
                                json.dumps({
                                    'event': 'initialized_channel',
                                    'data': new_init_channel_event_to_dict(event.args),
                                    'block_number': event.blockNumber,
                                    'txhash': event.transactionHash.hex(),
                                }))
                            temp_block = event.blockNumber if event.blockNumber > temp_block else temp_block

                    for _ in block_filter.get_new_entries():
                        ws.send(
                            json.dumps({
                                'event': 'block',
                                'data': {
                                    'number': g.chain.w3.eth.blockNumber,
                                },
                            }))
                        temp_block = g.chain.w3.eth.blockNumber if g.chain.w3.eth.blockNumber > temp_block else \
                            temp_block

                    if temp_block > latest_block:
                        latest_block = temp_block

                    gevent.sleep(1)
                except ValueError:
                    filters_initialized = False
            except WebSocketError:
                logger.info('Websocket connection closed, exiting loop')
                break
            except ConnectionError:
                logger.exception('ConnectionError in /events (is geth down?)')
                filters_initialized = False
                continue
            except Exception:
                logger.exception('Exception in /events, resetting filters')
                filters_initialized = False
                continue

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
