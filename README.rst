PolySwarm
=========

*API under development and may change*

Introduction
------------

This repository contains the end-to-end test network implementation of
Bounties as described in our whitepaper
(https://polyswarm.io/polyswarm-whitepaper.pdf). Offers are coming soon.
All contracts in this repo are subject to change.

Bounties
--------

Bounties in PolySwarm give enterprises the ability to submit artifacts
to PolySwarm and receive responses from experts on the maliciousness of
artifacts. Enterprises can leverage the HTTP API as an interface for
posting suspect artifacts to PolySwarm. Experts can use the same
interface to stream bounties and post their assertions (opinions) on
files of interest for which they have expertise.

Posting (Enterprise/Users)
~~~~~~~~~~~~~~~~~~~~~~~~~~

There are several components of each bounty posted:

-  Bounty fee which experts must pay to record their assertions
-  Bounty amount which is the initial reward offered to experts for
   examining the file
-  Artifact IPFS URI to fetch
-  Deadline
-  Bounty GUID
-  Arbiter verdicts
PolySwarm
=========

*API under development and may change*

Introduction
------------

This repository contains the end-to-end test network implementation of
Bounties as described in our whitepaper
(https://polyswarm.io/polyswarm-whitepaper.pdf). Offers are coming soon.
All contracts in this repo are subject to change.

Bounties
--------

Bounties in PolySwarm give enterprises the ability to submit artifacts
to PolySwarm and receive responses from experts on the maliciousness of
artifacts. Enterprises can leverage the HTTP API as an interface for
posting suspect artifacts to PolySwarm. Experts can use the same
interface to stream bounties and post their assertions (opinions) on
files of interest for which they have expertise.

Posting (Enterprise/Users)
~~~~~~~~~~~~~~~~~~~~~~~~~~

There are several components of each bounty posted:

-  Bounty fee which experts must pay to record their assertions
-  Bounty amount which is the initial reward offered to experts for
   examining the file
-  Artifact IPFS URI to fetch
-  Deadline
-  Bounty GUID
-  Arbiter verdicts

Enterprises can leverage the HTTP API as an interface for posting
suspect artifacts to PolySwarm.

Assertions
~~~~~~~~~~

Experts can use the same interface to stream bounties and post their
assertions (opinions) on files of interest for which they have
expertise.

An event-based API for streaming bounties is provided.

Assertions against posted bounties consist of:

-  A bid against the bounty
-  A determination of malicious-or-not (boolean)
-  Optional metadata (such as e.g. malware family) which provides
   value-add to the bounty poster

Verdicts
~~~~~~~~

Arbiters may settle bounties to trigger payment based on their
determination.

Offers
------

Offers are a work in progress, but will represent a direct offer from an
enterprise to a security expert to analyze an artifact. To issue an
offer, the enterprise will open a Raiden-style channel with the expert
and issue zero or more offers.

Running
-------

Steps:

0) Configure a private Ethereum testnet and an IPFS node
1) Install Truffle with ``npm i -g truffle``
2) Install Python3 and pip
3) Fetch repository and all submodules
4) Build truffle project ``truffle compile``
5) Deploy truffle project onto (local private) Ethereum chain
   ``truffle migrate``
6) Install python dependencies ``pip3 install -r requirements.txt``
7) Run server with ``python3 -m polyswarmd``

Docker
------

0) Build a docker image from ``docker/Dockerfile``, tag as
    ``polyswarm/polyswarmd``
1) Run with ``docker-compose -f docker/docker-compose.yml up``

Signing Transactions
--------------------
In the latest verions of Polyswarmd it moved away from unlocking the account in
geth. Now, all transactions are sent over a websocket where they can be individually signed. 

To add transaction signing to your polyswarmd dependent project you need to to
write/use something that follows the steps below..

0) Listen to the websocket at ``ws://localhost:31337/transactions``
1) Upon receiving JSON formatted message, parse the id, chainId, and transaction data
2) Sign the Transaction data with your private key
3) Return a JSON object containing the id, chainID, and signed data as data.

There is a javascript example embedded below, though you can use any 
other language.

.. code:: javascript

  const EthereumTx = require('ethereumjs-tx');
  const keythereum = require('keythereum');
  const WebSocket = require('isomorphic-ws');

  const ws = new WebSocket('ws://localhost:31337/transactions');

  const DATADIR = '/home/user/.ethereum/priv_testnet';
  const ADDRESS = '34e583cf9c1789c3141538eec77d9f0b8f7e89f2';
  const PASSWORD = 'password';

  const enc_key = keythereum.importFromFile(ADDRESS, DATADIR);
  const key = keythereum.recover(PASSWORD, enc_key);

  ws.onmessage = msg => {
    console.log(msg.data);
    const {id, data} = JSON.parse(msg.data);
    const {chainId} = data;
    console.log(data);
    const tx = new EthereumTx(data);
    tx.sign(key);

    ws.send(JSON.stringify({'id': id, 'chainId': chainId, 'data': tx.serialize().toString('hex')}));
  };

Common issues and solutions
---------------------------

gas required exceeds allowance or always failing transaction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**When posting an assertion**
The assertion targets an expired bounty. 

**Other times**
The wallet does not have any Nectar, or maybe not enough ETH for gas.
