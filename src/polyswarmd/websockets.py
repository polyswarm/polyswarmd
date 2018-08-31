import gevent
import json
import jsonschema
import logging
import sys
import time

from jsonschema.exceptions import ValidationError
from flask import request
from flask_sockets import Sockets
from geventwebsocket import WebSocketError

from polyswarmd.eth import web3 as web3_chains, bounty_registry as bounty_chains, offer_registry
from polyswarmd.config import chain_id as chain_ids
from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict, state_to_dict, new_init_channel_event_to_dict, new_quorum_event_to_dict, settled_bounty_event_to_dict, revealed_assertion_event_to_dict


def init_websockets(app):
    sockets = Sockets(app)
    start_time = time.time()

    @sockets.route('/events')
    def events(ws):
        chain = request.args.get('chain', 'home')
        if chain != 'side' and chain != 'home':
            logging.error('Chain must be either home or side')
            ws.close()

        web3 = web3_chains[chain]
        bounty_registry = bounty_chains[chain]

        block_filter = web3.eth.filter('latest')
        bounty_filter = bounty_registry.eventFilter('NewBounty')
        assertion_filter = bounty_registry.eventFilter('NewAssertion')
        verdict_filter = bounty_registry.eventFilter('NewVerdict')
        quorum_filiter = bounty_registry.eventFilter('QuorumReached')
        settled_filter = bounty_registry.eventFilter('BountySettled')
        reveal_filter = bounty_registry.eventFilter('RevealedAssertion')

        init_filter = offer_registry.eventFilter('InitializedChannel')

        ws.send(
            json.dumps({
                'event': 'connected',
                'data': {
                    'start_time': str(start_time),
                }
            }))

        while not ws.closed:
            try:
                for event in block_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event': 'block',
                            'data': {
                                'number': web3.eth.blockNumber,
                            },
                        }))

                for event in bounty_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'bounty',
                            'data':
                            new_bounty_event_to_dict(event.args),
                        }))

                for event in assertion_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'assertion',
                            'data':
                            new_assertion_event_to_dict(event.args),
                        }))

                for event in reveal_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'reveal',
                            'data':
                            revealed_assertion_event_to_dict(event.args),
                        }))

                for event in verdict_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'verdict',
                            'data':
                            new_verdict_event_to_dict(event.args),
                        }))

                for event in quorum_filiter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'quorum',
                            'data':
                            new_quorum_event_to_dict(event.args),
                        }))

                for event in settled_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'settled_bounty',
                            'data':
                            settled_bounty_event_to_dict(event.args),
                        }))

                for event in init_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'initialized_channel',
                            'data':
                            new_init_channel_event_to_dict(event.args),
                        }))

                gevent.sleep(1)
            except WebSocketError:
                break
            except Exception as e:
                logging.error('Error in /events: %s', e)
                continue

    # for receive messages about offers that might need to be signed
    @sockets.route('/messages/<uuid:guid>')
    def messages(ws, guid):
        try:
            while not ws.closed:
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
                except ValidationError as e:
                    logging.error('Invalid JSON: %s', e)

                state_dict = state_to_dict(body['state'])
                state_dict['guid'] = guid.int

                ws.send(
                    json.dumps({
                        'type': body['type'],
                        'raw_state': body['state'],
                        'state': state_dict
                    }))
        except:
            pass
