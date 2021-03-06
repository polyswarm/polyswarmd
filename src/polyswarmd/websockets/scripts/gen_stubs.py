#!/usr/bin/env python3
"""gen_stubs.py
This script generates the additional stubs for polyswarmd messages

You can run it from src/polyswarmd like so:

python3 -m websockets.scripts.gen_stubs
"""
import inspect
import re
from typing import Any

from polyswarmd.websockets import messages

HEADER = """\"\"\"
This file has been automatically generated by scripts/gen_stubs.py
\"\"\"

from typing import Any, Dict, Generic, List, Mapping, Optional, TypeVar

try:
    from typing import TypedDict  # noqa
except ImportError:
    from mypy_extensions import TypedDict  # noqa

D = TypeVar('D')
E = TypeVar('E')


class EventData(Mapping):
    "Event data returned from web3 filter requests"
    args: Dict[str, Any]
    event: str
    logIndex: int
    transactionIndex: int
    transactionHash: bytes
    address: str
    blockHash: bytes
    blockNumber: int


class WebsocketEventMessage(Generic[D], Mapping):
    "An Polyswarm WebSocket message"
    event: str
    data: D
    block_number: Optional[int]
    txhash: Optional[str]
"""


def gen_stub(cls: Any, klass: str = None):
    """Return a string of the type returned by that class's schema extraction"""
    name = cls.contract_event_name
    # Create a new `TypedDict' definition
    tname = f'{name}MessageData'
    type_str = f"{tname} = TypedDict('{tname}', {cls.schema.build_annotations()})"
    return re.sub(r"'?(typing|zv|builtin).(\w*)'?", r'\2', type_str)


if __name__ == "__main__":
    print(HEADER)
    for dts in [messages.EventLogMessage, messages.WebsocketFilterMessage]:
        for scls in dts.__subclasses__():
            if 'schema' in dir(scls):
                klass = inspect.getsource(scls)
                print(gen_stub(scls, klass))
                print("\n")
    print("# Latest event's data type is not synthesized from a schema.")
    print("# If it's type changes, update gen_stubs.py")
    print("""LatestEventMessageData = TypedDict('LatestEventMessageData', {'number': int})""")
