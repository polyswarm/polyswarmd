# polyswarmd - The PolySwarm Daemon

*API under development and is subject to change*

## Introduction

`polyswarmd` is a convenience daemon that provides a simple RPC API for interacting with the PolySwarm marketplace. Specifically, `polyswarmd` handles interaction with Ethereum and IPFS nodes on clients' behalf.


## Usage

New developers are encouraged to visit the [PolySwarm Documentation](https://docs.polyswarm.io) and build on top of [`polyswarm-client`](https://github.com/polyswarm/polyswarm-client) rather than directly writing code against the comparatively low-level `polyswarmd`.

### `make`

There are a selection of useful rules covering routine tasks made in the project `Makefile`,

- `make test` - Run all `pytest` unittests & doctests
    + `make quicktest` - Run all "NOT SLOW" tests (PolyswarmD has some
                        slow-running tests to verify certain WebSocket behavior,
                        this will skip those)
    + `make coverage` - Print a test coverage report
- `make lint` - Linting the source directory with
            [yapf](https://github.com/google/yapf),
            [isort](https://github.com/timothycrosley/isort)
            [mypy](https://mypy.readthedocs.io/en/latest/),
            [flake8](http://flake8.pycqa.org/en/latest/) as well as running
            doctests for `polyswarmd.websockets` & verifying `requirements*.txt`
            is sorted.
    + `make mypy` - Run [mypy](https://mypy.readthedocs.io/en/stable/) type
                   checking
- `make format` - format source code in Polyswarm style
    + `make format-tests` - format test code
    + `make format-requirements` - format `requirements*.txt`
- `make clean` - Clean `build/`, `*.pyc` and more
- `make help` - Print available rules

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

