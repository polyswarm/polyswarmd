from concurrent.futures import ThreadPoolExecutor
import gevent
import json

from gevent.lock import BoundedSemaphore
from requests.exceptions import ConnectionError
from polyswarmartifact.schema import Bounty as BountyMetadata
from requests_futures.sessions import FuturesSession

from polyswarmd.utils import *


class GethRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open websockets

    """
    def __init__(self, chain):
        self.chain = chain
        self.session = FuturesSession(executor=ThreadPoolExecutor(32),
                                      adapter_kwargs={'max_retries': 3})
        self.assertion_filter = None
        self.block_filter = None
        self.bounty_filter = None
        self.deprecated_filter = None
        self.fee_filter = None
        self.init_filter = None
        self.quorum_filiter = None
        self.reveal_filter = None
        self.settled_filter = None
        self.vote_filter = None
        self.window_filter = None
        self.websockets_lock = BoundedSemaphore(1)
        self.websockets = None

    def broadcast(self, message):
        logger.debug('Sending: %s', message)
        with self.websockets_lock:
            for ws in self.websockets:
                logger.critical('Sending ws %s %s', ws, message)
                ws.send(json.dumps(message))

    def flush_filters(self):
        self.block_filter.get_new_entries()
        self.fee_filter.get_new_entries()
        self.window_filter.get_new_entries()
        self.bounty_filter.get_new_entries()
        self.assertion_filter.get_new_entries()
        self.vote_filter.get_new_entries()
        self.quorum_filiter.get_new_entries()
        self.settled_filter.get_new_entries()
        self.reveal_filter.get_new_entries()
        self.deprecated_filter.get_new_entries()
        if self.init_filter:
            self.init_filter.get_new_entries()

    # noinspection PyBroadException
    def poll(self, ipfs_uri):
        logger.info('Starting greenlet')
        self.setup_filters()
        from polyswarmd.bounties import substitute_ipfs_metadata
        while True:
            gevent.sleep(1)
            # Check that there is some websocket connection
            with self.websockets_lock:
                skip = not self.websockets

            # If there isn't, hit the filters anyway, since we don't want old data
            if skip:
                continue

            try:
                for event in self.fee_filter.get_new_entries():
                    fee_update = {
                        'event': 'fee_update',
                        'data': fee_update_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(fee_update)

                for event in self.window_filter.get_new_entries():
                    window_update = {
                        'event': 'window_update',
                        'data': window_update_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(window_update)

                for event in self.bounty_filter.get_new_entries():
                    bounty = {
                        'event': 'bounty',
                        'data': new_bounty_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    metadata = bounty['data'].get('metadata', None)
                    if metadata:
                        bounty['data']['metadata'] = substitute_ipfs_metadata(metadata,
                                                                              validate=BountyMetadata.validate,
                                                                              ipfs_root=ipfs_uri,
                                                                              session=self.session)
                    else:
                        bounty['data']['metadata'] = None

                    self.broadcast(bounty)

                for event in self.assertion_filter.get_new_entries():
                    assertion = {
                        'event': 'assertion',
                        'data': new_assertion_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(assertion)

                for event in self.reveal_filter.get_new_entries():
                    reveal = {
                        'event': 'reveal',
                        'data': revealed_assertion_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    reveal['data']['metadata'] = substitute_ipfs_metadata(reveal['data'].get('metadata', ''),
                                                                          ipfs_root=ipfs_uri,
                                                                          session=self.session)

                    self.broadcast(reveal)

                for event in self.vote_filter.get_new_entries():
                    vote = {
                        'event': 'vote',
                        'data': new_vote_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(vote)

                for event in self.quorum_filiter.get_new_entries():
                    quorum = {
                        'event': 'quorum',
                        'data': new_quorum_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(quorum)

                for event in self.settled_filter.get_new_entries():
                    settled_bounty = {
                        'event': 'settled_bounty',
                        'data': settled_bounty_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex(),
                    }
                    self.broadcast(settled_bounty)

                for event in self.deprecated_filter.get_new_entries():
                    deprecated = {
                        'event': 'deprecated',
                        'data': deprecated_event_to_dict(event.args),
                        'block_number': event.blockNumber,
                        'txhash': event.transactionHash.hex()
                    }
                    self.broadcast(deprecated)

                if self.init_filter is not None:
                    for event in self.init_filter.get_new_entries():
                        initialized_channel = {
                            'event': 'initialized_channel',
                            'data': new_init_channel_event_to_dict(event.args),
                            'block_number': event.blockNumber,
                            'txhash': event.transactionHash.hex(),
                        }
                        self.broadcast(initialized_channel)
                for _ in self.block_filter.get_new_entries():
                    block = {
                        'event': 'block',
                        'data': {
                            'number': self.chain.w3.eth.blockNumber,
                        },
                    }
                    self.broadcast(block)
            except ConnectionError:
                logger.exception('ConnectionError in filters (is geth down?)')
                continue
            except Exception:
                logger.exception('Exception in filter checks, resetting filters')
                self.flush_filters()
                continue

    def register(self, ws):
        """
        Register a websocket with the rpc nodes
        Gets all events going forward
        :param ws: websocket to send to
        """
        start = False
        # Cross greenlet list
        with self.websockets_lock:
            if self.websockets is None:
                start = True
                self.websockets = []
            elif not self.websockets:
                # Clear the filters of old data
                logger.critical('Clearing out of date filter events.')
                self.flush_filters()

            self.websockets.append(ws)

        if start:
            logger.debug('First websocket registered, starting greenlet')
            from polyswarmd import app
            ipfs_uri = app.config['POLYSWARMD'].ipfs_uri
            gevent.spawn(self.poll, ipfs_uri)

    def setup_filters(self):
        self.block_filter = self.chain.w3.eth.filter('latest')
        self.fee_filter = self.chain.bounty_registry.contract.eventFilter('FeesUpdated')
        self.window_filter = self.chain.bounty_registry.contract.eventFilter('WindowsUpdated')
        self.bounty_filter = self.chain.bounty_registry.contract.eventFilter('NewBounty')
        self.assertion_filter = self.chain.bounty_registry.contract.eventFilter('NewAssertion')
        self.vote_filter = self.chain.bounty_registry.contract.eventFilter('NewVote')
        self.quorum_filiter = self.chain.bounty_registry.contract.eventFilter('QuorumReached')
        self.settled_filter = self.chain.bounty_registry.contract.eventFilter('SettledBounty')
        self.reveal_filter = self.chain.bounty_registry.contract.eventFilter('RevealedAssertion')
        self.deprecated_filter = self.chain.bounty_registry.contract.eventFilter('Deprecated')
        self.init_filter = None
        if self.chain.offer_registry.contract is not None:
            self.init_filter = self.chain.offer_registry.contract.eventFilter('InitializedChannel')

    def unregister(self, ws):
        logger.debug('Unregistering websocket %s', ws)
        with self.websockets_lock:
            if ws in self.websockets:
                logger.critical('Removing ws %s', ws)
                self.websockets.remove(ws)
