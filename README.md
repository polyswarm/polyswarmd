# polyswarmd - The PolySwarm Daemon

*API under development and is subject to change*

## Introduction

`polyswarmd` is a convenience daemon that provides a simple REST API for interacting with the PolySwarm marketplace. Specifically, `polyswarmd` handles interaction with Ethereum and IPFS nodes on clients' behalf.


## Usage

New developers are encouraged to visit the [PolySwarm Documentation](https://docs.polyswarm.io) and build on top of [`polyswarm-client`](https://github.com/polyswarm/polyswarm-client) rather than directly code against the comparatively low-level `polyswarmd`.


## Troubleshooting

### gas required exceeds allowance or always failing transaction

**When posting an assertion**
The assertion targets an expired bounty.

**Other times**
The wallet does not have any Nectar, or maybe not enough ETH for gas.
