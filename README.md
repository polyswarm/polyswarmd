# polyswarmd - The PolySwarm Daemon

*API under development and is subject to change*

## Introduction

`polyswarmd` is a convenience daemon that provides a simple REST API for interacting with the PolySwarm marketplace. Specifically, `polyswarmd` handles interaction with Ethereum and IPFS nodes on clients' behalf.


## Usage

New developers are encouraged to visit the [PolySwarm Documentation](https://docs.polyswarm.io) and build on top of [`polyswarm-client`](https://github.com/polyswarm/polyswarm-client) rather than directly writing code against the comparatively low-level `polyswarmd`.


### Linting and Types
PolyswarmD has some [mypy](https://mypy.readthedocs.io/en/latest/) types and is configured to type existing untyped PolyswarmD code (although it lacks types for many external libraries, these can be generated with `stubgen`, although in my experience the gain isn't worth the cost of setting them up).

### Linting
The `Makefile` includes recipe (`make lint`)) for linting the repository with [yapf](https://github.com/google/yapf), [isort](https://github.com/timothycrosley/isort) [mypy](https://mypy.readthedocs.io/en/latest/), [flake8](http://flake8.pycqa.org/en/latest/) as well as running doctests for `polyswarmd.websockets`.

The configuration files for each are an approximation of my own reading of _"Polyswarm style"_. If you'd like to use these settings in other projects, you can copy `setup.cfg`. `PolyswarmD` serves as the backbone for many projects, so it's configuration should also function as a reasonable base for other project's linting style; if something changes, please open a PR to add or modify it's linting config in `setup.cfg`.

#### Formatting
`make format` applies formatting to the files in `src/polyswarmd` in-place, rather than just emitting suggestions them to the user.

### Generating stubs
`make genstubs` will print dynamically generated type-stubs for the polyswarm Websocket messages. The script which is ultimately responsible for generating these stubs is located in `src/polyswarmd/websockets/scripts/gen_stubs.py`

## Unit tests
`make tests` will run PolyswarmD's unit test suite. 

If you'd like to update the contract ABIs fixtures included with this repository, you can do so with a copy of [contractor](https://github.com/polyswarm/contractor) by compiling & copying to `tests/fixtures/config/chain`:

```console
foo@bar:~/polyswarm/contractor$ contractor compile
INFO:contractor.compiler:Compiling OfferMultiSig.sol, ArbiterStaking.sol, NectarToken.sol, ERC20Relay.sol, BountyRegistry.sol, OfferRegistry.sol
INFO:contractor.compiler:Writing build/OfferMultiSig.json
INFO:contractor.compiler:Writing build/ArbiterStaking.json
INFO:contractor.compiler:Writing build/NectarToken.json
INFO:contractor.compiler:Writing build/ERC20Relay.json
INFO:contractor.compiler:Writing build/BountyRegistry.json
INFO:contractor.compiler:Writing build/OfferRegistry.json

foo@bar:~/polyswarm/contractor$ cp build/*.json ~/polyswarm/polyswarmd/tests/fixtures/config/chain
```

## Example Config

```yaml
artifact:
  max_size: 34603008
  fallback_max_size: 10485760
  limit: 256
  library:
    module: polyswarmd.services.artifact.ipfs
    class_name: IpfsServiceClient
    args:
      - http://localhost:5001
community: gamma
eth:
  trace_transactions: true
  consul:
    uri: http://localhost:8500
  # directory: /path/to/config 
profiler:
  enabled: false
  # db_uri: http://db:1234
redis:
  uri: redis://localhost:6379
websocket:
  enabled: true
```

