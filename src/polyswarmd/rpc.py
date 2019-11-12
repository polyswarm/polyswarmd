import json
import time

from requests.exceptions import ConnectionError

import gevent
from filter_manager import (FilterManager,
                            Deprecated, FeesUpdated, InitializedChannel,
                            LatestEvent, NewAssertion, NewBounty, NewVote,
                            QuorumReached, RevealedAssertion, SettledBounty,
                            WindowsUpdated)
from gevent.lock import BoundedSemaphore


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    def __init__(self, chain):
        self.chain = chain
        self.block_filter = None
        self.websockets_lock = BoundedSemaphore(1)
        self.websockets = None
        self.fmanager = FilterManager()

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
                ws.send(message)

    # noinspection PyBroadException
    def poll(self):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        """
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
                for event in self.fmanager.new_ws_entries():
                    self.broadcast(event)
            except ConnectionError:
                logger.exception('ConnectionError in filters (is geth down?)')
                continue
            except Exception:
                logger.exception('Exception in filter checks, restarting greenlet')
                # Creates a new greenlet with all new filters and let's this one die.
                gevent.spawn(self.poll)
                return

    def setup_filters(self):
        bounty_filters = [
            FeesUpdated,
            WindowsUpdated,
            NewBounty,
            NewAssertion,
            NewVote,
            QuorumReached,
            SettledBounty,
            RevealedAssertion,
            Deprecated
        ]
        for cls in bounty_filters:
            self.fmanager.register(cls, self.chain.bounty_registry.contract.eventFilter(cls.filter_id))

        self.fmanager.register(LatestEvent, self.chain.w3.eth.filter('latest'))

        if self.chain.offer_registry.contract:
            self.fmanager.register(InitializedChannel, self.chain.offer_registry.contract.eventFilter('InitializedChannel'))

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
                self.event_filters.flush()

            self.websockets.append(ws)

        if start:
            logger.debug('First WebSocket registered, starting greenlet')
            gevent.spawn(self.poll)

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
