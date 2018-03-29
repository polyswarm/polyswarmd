import json
import os
import unittest
import polyswarmd
from polyswarmd import check_transaction
from flask import request_started, g

from web3.module import Module

snapshot = None

class TestRPC(Module):
    def evm_snapshot(self):
        return self.web3.manager.request_blocking('evm_snapshot', [])

    def evm_revert(self, snapshot):
        return self.web3.manager.request_blocking('evm_revert', [snapshot])

    def evm_increaseTime(self, duration):
        return self.web3.manager.request_blocking('evm_increaseTime', [duration])

    def evm_mine(self, blocks):
        for _ in range(blocks):
            self.web3.manager.request_blocking('evm_mine', [])

TestRPC.attach(polyswarmd.web3, 'testrpc')

class PolyswarmTestCase(unittest.TestCase):

    def setUp(self):
        global snapshot

        self.maxDiff = None
        self.app = polyswarmd.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        self.web3 = polyswarmd.web3
        self.accounts = self.web3.eth.accounts
        self.owner = self.accounts[0]
        self.user = self.accounts[1]
        self.expert = self.accounts[2]
        self.arbiter = self.accounts[3]

        if snapshot is None:
            # Initialize our state
            for account in self.web3.eth.accounts:
                tx = polyswarmd.nectar_token.functions.mint(account, self.web3.toWei(1000, 'ether')).transact({'from': self.owner})
                self.assertTrue(check_transaction(tx))

            tx = polyswarmd.nectar_token.functions.enableTransfers().transact({'from': self.owner})
            self.assertTrue(check_transaction(tx))

            tx = polyswarmd.bounty_registry.functions.addArbiter(self.arbiter).transact({'from': self.owner})
            self.assertTrue(check_transaction(tx))

            snapshot = self.web3.testrpc.evm_snapshot()
        else:
            self.web3.testrpc.evm_revert(snapshot)

    def getResult(self, rv):
        self.assertEqual(rv.status_code, 200)
        data = json.loads(rv.data.decode('utf-8'))
        self.assertEqual(data['status'], 'OK')
        return data.get('result', None)

    def test_get_accounts_balance_eth(self):
        rv = self.client.get('/accounts/' + self.user + '/balance/eth')
        result = self.getResult(rv)
        self.assertEqual(result, str(self.web3.toWei(1000000, 'ether')))

    def test_get_accounts_balance_nct(self):
        rv = self.client.get('/accounts/' + self.user + '/balance/nct')
        result = self.getResult(rv)
        self.assertEqual(result, str(self.web3.toWei(1000, 'ether')))


if __name__ == '__main__':
    unittest.main()
