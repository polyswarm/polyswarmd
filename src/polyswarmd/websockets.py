import json

import jsonschema
from jsonschema.exceptions import ValidationError
from flask_sockets import Sockets
import gevent
import gevent.queue
from hexbytes import HexBytes

from polyswarmd.eth import web3 as web3_chains, bounty_registry, chain_id as chain_ids
from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict

web3 = web3_chains['side']

# TODO: This needs some tweaking to work for multiple accounts / concurrent
# requests, mostly dealing with nonce calculation
class TransactionQueue(object):
    def __init__(self, chain):
        self.inner = gevent.queue.Queue()
        self.lock = gevent.lock.Semaphore()
        self.dict = dict()
        self.id_ = 0
        self.pending = 0
        self.chain = chain

    def acquire(self):
        self.lock.acquire()

    def release(self):
        self.lock.release()

    def complete(self, id_, txhash):
        self.acquire()
        self.dict[id_].set_result(txhash)
        self.pending -= 1
        self.release()

    def send_transaction(self, call, account):
        self.acquire()

        nonce = web3_chains[self.chain].eth.getTransactionCount(account) + self.pending
        self.pending += 1

        tx = call.buildTransaction({
            'nonce': nonce,
            'chainId': int(chain_ids[self.chain]),
        })
        result = gevent.event.AsyncResult()

        self.dict[self.id_] = result
        self.inner.put((self.id_, tx))
        self.id_ += 1

        self.release()

        return result

    def __iter__(self):
        return iter(self.inner)

# We do two of these so we can maintain the nonce. We can't be combining our pending tx count
side_transaction_queue = TransactionQueue('side')
home_transaction_queue = TransactionQueue('home')

def init_websockets(app):
    sockets = Sockets(app)

    @sockets.route('/events')
    def events(ws):
        block_filter = web3.eth.filter('latest')
        bounty_filter = bounty_registry.eventFilter('NewBounty')
        assertion_filter = bounty_registry.eventFilter('NewAssertion')
        verdict_filter = bounty_registry.eventFilter('NewVerdict')

        try:
            while not ws.closed:
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

                gevent.sleep(1)
        except:
            pass

    @sockets.route('/transactions')
    def transactions(ws):
        def home_queue_greenlet():
            for (id_, tx) in home_transaction_queue:
                ws.send(json.dumps({'id': id_, 'data': tx}))

        def side_queue_greenlet():
            for (id_, tx) in side_transaction_queue:
                ws.send(json.dumps({'id': id_, 'data': tx}))

        # If we can handle the pending tx stuff above, we combine this to one
        home_qgl = gevent.spawn(home_queue_greenlet)
        side_qgl = gevent.spawn(side_queue_greenlet)

        schema = {
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                },
                'chainId': {
                    'type': 'integer',
                },
                'data': {
                    'type': 'string',
                    'maxLength': 4096,
                },
            },
            'required': ['id', 'chainId', 'data'],
        }

        try:
            while not ws.closed:
                msg = ws.receive()
                if not msg:
                    break

                body = json.loads(msg)
                try:
                    jsonschema.validate(body, schema)
                except ValidationError as e:
                    print('Invalid JSON: ' + e.message)

                id_ = body['id']
                data = body['data']
                chain_id = body['chainId']

                chain_label = ''
                for k, v in chain_ids.items():
                    if int(v) == chain_id:
                        chain_label = k
                        break

                txhash = web3_chains[chain_label].eth.sendRawTransaction(HexBytes(data))
                print('GOT TXHASH:', txhash)
                if chain_label == 'side':
                    side_transaction_queue.complete(id_, txhash)
                elif chain_label == 'home':
                    home_transaction_queue.complete(id_, txhash)
                else:
                    print('Invalid ChainId. Not our sidechain or homechain.')

        finally:
            home_qgl.kill()
            side_qgl.kill()
