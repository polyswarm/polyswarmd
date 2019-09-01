import time
from concurrent.futures import ThreadPoolExecutor
import gevent
import json

from gevent.lock import BoundedSemaphore
from requests.exceptions import ConnectionError
from polyswarmartifact.schema import Bounty as BountyMetadata
from requests_futures.sessions import FuturesSession

from polyswarmd.utils import *


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
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

    @staticmethod
    def compute_sleep(diff):
        """ Adjusts sleep based on the difference of last iteration.
        If last iteration took over 500 millis, adjust this sleep lower. Otherwise, return 500


        :param diff: time in millis
        :return: sleep time in millis
        """
        if diff > 500:
            sleep = 1000 - diff
            return sleep if sleep > 0 else 0
        else:
            return 500

    def broadcast(self, message):
        """
        Send a message to all connected WebSockets
        :param message: dict to be converted to json and sent
        """
        logger.debug('Sending: %s', message)
        with self.websockets_lock:
            for ws in self.websockets:
                logger.debug('Sending WebSocket %s %s', ws, message)
                ws.send(json.dumps(message))

    def flush_filters(self):
        """
        Clear filters of existing entires
        """
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
    def poll(self, artifact_client):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        :param artifact_client: ArtifactClient for making requests to artifact service
        """
        self.setup_filters()
        from polyswarmd.bounties import substitute_metadata
        last = time.time() * 1000 // 1
        while True:
            now = time.time() * 1000 // 1
            gevent.sleep(EthereumRpc.compute_sleep(now - last) / 1000)
            last = now
            # If there is no websocket, exit greenlet
            with self.websockets_lock:
                if not self.websockets:
                    # Set websockets to None so the greenlet is recreated on new join
                    self.websockets = None
                    return

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
                        bounty['data']['metadata'] = substitute_metadata(metadata, validate=BountyMetadata.validate,
                                                                         artifact_client=artifact_client,
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
                    reveal['data']['metadata'] = substitute_metadata(reveal['data'].get('metadata', ''),
                                                                     artifact_client=artifact_client,
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
                logger.exception('Exception in filter checks, restarting greenlet')
                # Creates a new greenlet with all new filters and let's this one die.
                gevent.spawn(self.poll, artifact_client)
                break

    def register(self, ws):
        """
        Register a WebSocket with the rpc nodes
        Gets all events going forward
        :param ws: WebSocket wrapper to register
        """
        start = False
        # Cross greenlet list
        with self.websockets_lock:
            if self.websockets is None:
                start = True
                self.websockets = []
            elif not self.websockets:
                # Clear the filters of old data.
                # Possible when last WebSocket closes & a new one opens before the 1 poll sleep ends
                logger.debug('Clearing out of date filter events.')
                self.flush_filters()

            self.websockets.append(ws)

        if start:
            logger.debug('First WebSocket registered, starting greenlet')
            from polyswarmd import app
            artifact_client = app.config['POLYSWARMD'].artifact_client
            gevent.spawn(self.poll, artifact_client)

    def setup_filters(self):
        """
        Start all required filters on the eth node.
        """
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
        """
        Remove a Websocket wrapper object
        :param ws: WebSocket to remove
        """
        logger.debug('Unregistering WebSocket %s', ws)
        with self.websockets_lock:
            if ws in self.websockets:
                logger.debug('Removing WebSocket %s', ws)
                self.websockets.remove(ws)
