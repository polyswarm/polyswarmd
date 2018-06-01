import json

import jsonschema
from jsonschema.exceptions import ValidationError
from flask_sockets import Sockets
import gevent
import gevent.queue
from hexbytes import HexBytes

from polyswarmd.eth import web3 as web3_chains, bounty_registry as bounty_chains
from polyswarmd.config import chain_id as chain_ids
from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict

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
transaction_queue = dict()
transaction_queue['home'] = TransactionQueue('home')
transaction_queue['side'] = TransactionQueue('side')

def init_websockets(app):
    sockets = Sockets(app)

    @sockets.route('/events/<chain>')
    def events(ws, chain):
        if chain != 'side' and chain != 'home':
            print('Chain must be either home or side')
            ws.close()

        web3 = web3_chains[chain]
        bounty_registry = bounty_chains[chain]

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
            for (id_, tx) in transaction_queue['home']:
                ws.send(json.dumps({'id': id_, 'data': tx}))

        def side_queue_greenlet():
            for (id_, tx) in transaction_queue['side']:
                ws.send(json.dumps({'id': id_, 'data': tx}))

        # If we can handle the pending tx stuff above, we combine this to one
        qgl = dict()
        qgl['home'] = gevent.spawn(home_queue_greenlet)
        qgl['side'] = gevent.spawn(side_queue_greenlet)

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

                queue = transaction_queue.get(chain_label)
                if queue is not None:
                    queue.complete(id_, txhash)
                else:
                    print('Invalid ChainId ' + chain_id)

        finally:
            qgl['home'].kill()
            qgl['side'].kill()
