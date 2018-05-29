PolySwarm Alpha
===============

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

Examples
--------

**Upload an artifact**
``curl -F file=@foo http://localhost:31337/artifacts``

**Get artifact**
``curl http://localhost:31337/artifacts/QmTcKufUeYYdT4YYAZsv25FNdeJ9q2NyCKLW3CeN4H69fw/0``

**Unlock account (likely to change)**
``curl -H 'Content-Type: application/json' -d '{"password": "password"}' http://localhost:31337/accounts/af8302a3786a35abeddf19758067adc9a23597e5/unlock``

**Post bounty**
``curl -H 'Content-Type: application/json' -d '{"amount": "62500000000000000", "uri": "QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6", "duration": 10}' http://localhost:31337/bounties``

**Get bounty**
``curl http://localhost:31337/bounties/5caa7538-3cb6-44ca-9def-ca0c87e6f0fa``

**Post assertion**
``curl -H 'Content-Type: application/json' -d '{"bid": "62500000000000000", "mask": [true], "verdicts": [true], "metadata": "foo"}' http://localhost:31337/bounties/5caa7538-3cb6-44ca-9def-ca0c87e6f0fa/assertions``

**Get assertion**
``curl http://localhost:31337/bounties/5caa7538-3cb6-44ca-9def-ca0c87e6f0fa/assertions/0``

**Settle bounty (arbiter)**
``curl -H 'Content-Type: application/json' -d '{"verdicts": [true]}' http://localhost:31337/bounties/5caa7538-3cb6-44ca-9def-ca0c87e6f0fa/settle``

Common issues and solutions
---------------------------

gas required exceeds allowance or always failing transaction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This error message appears when you post an assertion that targets an expired bounty. 
