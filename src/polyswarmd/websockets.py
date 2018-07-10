import gevent
import json
import jsonschema
import sys

from jsonschema.exceptions import ValidationError
from flask import request
from flask_sockets import Sockets
from geventwebsocket import WebSocketError

from polyswarmd.eth import web3 as web3_chains, bounty_registry as bounty_chains, offer_registry
from polyswarmd.config import chain_id as chain_ids
from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict, state_to_dict, new_init_channel_event_to_dict

def init_websockets(app):
    sockets = Sockets(app)

    @sockets.route('/events')
    def events(ws):
        chain = request.args.get('chain', 'home')
        if chain != 'side' and chain != 'home':
            print('Chain must be either home or side', file=sys.stderr)
            ws.close()

        web3 = web3_chains[chain]
        bounty_registry = bounty_chains[chain]

        block_filter = web3.eth.filter('latest')
        bounty_filter = bounty_registry.eventFilter('NewBounty')
        assertion_filter = bounty_registry.eventFilter('NewAssertion')
        verdict_filter = bounty_registry.eventFilter('NewVerdict')

        init_filter = offer_registry.eventFilter('InitializedChannel')

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

                for event in verdict_filter.get_new_entries():
                    ws.send(
                        json.dumps({
                            'event':
                            'verdict',
                            'data':
                            new_verdict_event_to_dict(event.args),
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
                print('Error in /events:', e, file=sys.stderr)
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
                    print('Invalid JSON:', e, file=sys.stderr)

                state_dict = state_to_dict(body['state'])
                state_dict['guid'] = guid.int

                ws.send(
                    json.dumps({
                        'type':
                        body['type'],
                        'raw_state':
                        body['state'],
                        'state':
                        state_dict
                    }))
        except:
            pass
