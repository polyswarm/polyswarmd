from flask_sockets import Sockets
from gevent import sleep

from polyswarmd.eth import web3, bounty_registry

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
                    ws.send(json.dumps({
                        'event': 'block',
                        'data': {
                            'number': web3.eth.blockNumber,
                        },
                    }))

                for event in bounty_filter.get_new_entries():
                    ws.send(json.dumps({
                        'event': 'bounty',
                        'data': new_bounty_event_to_dict(event.args),
                    }))

                for event in assertion_filter.get_new_entries():
                    ws.send(json.dumps({
                        'event': 'assertion',
                        'data': new_assertion_event_to_dict(event.args),
                    }))

                for event in verdict_filter.get_new_entries():
                    ws.send(json.dumps({
                        'event': 'verdict',
                        'data': new_verdict_event_to_dict(event.args),
                    }))

                sleep(1)
        except:
            return

    @sockets.route('/transactions')
    def transactions(ws):
        pass
