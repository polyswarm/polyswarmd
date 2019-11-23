# polyswarmd - The PolySwarm Daemon

*API under development and is subject to change*

## Introduction

`polyswarmd` is a convenience daemon that provides a simple REST API for interacting with the PolySwarm marketplace. Specifically, `polyswarmd` handles interaction with Ethereum and IPFS nodes on clients' behalf.


## Usage

New developers are encouraged to visit the [PolySwarm Documentation](https://docs.polyswarm.io) and build on top of [`polyswarm-client`](https://github.com/polyswarm/polyswarm-client) rather than directly writing code against the comparatively low-level `polyswarmd`.


### Linting and Types
PolyswarmD has some [mypy](https://mypy.readthedocs.io/en/latest/) types and is configured to type existing untyped PolyswarmD code (although it lacks types for many external libraries, these can be generated with `stubgen`, although in my experience the gain isn't worth the cost of setting them up).

### Linting
A script for linting the repository with [yapf](https://github.com/google/yapf), [isort](https://github.com/timothycrosley/isort) [mypy](https://mypy.readthedocs.io/en/latest/), [flake8](http://flake8.pycqa.org/en/latest/) as well as running doctests for `polyswarmd.websockets`, which lives at `./scripts/lint.sh`.

The configuration files for each are an approximation of my own reading of _"Polyswarm style"_. If you'd like to use these settings in other projects, you can copy `setup.cfg`. `PolyswarmD` serves as the backbone for many projects, so it's configuration should also function as a reasonable base for other project's linting style; if something changes, please open a PR to add or modify it's linting config in `setup.cfg`.

#### Formatting
`./scripts/lint.sh` can be run with the `-i` (in-place update) flag, which causes it to prompt the user to format all the source files located in `src/polyswarmd/`

### Generating stubs
`./scripts/lint.sh` can be run with `--stubs` flag to print dynamically generated type-stubs for the polyswarm Websocket messages. The script which is ultimately responsible for generating these stubs is located in `src/polyswarmd/websockets/scripts/gen_stubs.py`

