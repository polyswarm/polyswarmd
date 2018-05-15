import json
import gevent
import gevent.queue

from flask_sockets import Sockets

from polyswarmd.eth import web3, bounty_registry
from polyswarmd.bounties import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict


class TransactionQueue(object):
    def __init__(self):
        self.inner = gevent.queue.Queue()
        self.lock = gevent.lock.Semaphore()
        self.dict = dict()
        self.chain_id = web3.net.version

    def send_transaction(self, call, account):
        nonce = web3.eth.getTransactionCount(account)
        tx = call.buildTransaction({'nonce:': nonce, 'chainId': self.chain_id})

        result = gevent.event.AsyncResult()

        self.lock.acquire()
        self.dict[nonce] = (result, tx)
        self.inner.put(tx)
        self.lock.release()

    def __iter__(self):
        return iter(self.inner)


transaction_queue = TransactionQueue()


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
            return

    @sockets.route('/transactions')
    def transactions(ws):
        def queue_greenlet():
            for tx in transaction_queue:
                ws.send(json.dumps(tx))

        def websocket_greenlet():
            pass

        gevent.joinall([gevent.spawn(queue_greenlet)])
