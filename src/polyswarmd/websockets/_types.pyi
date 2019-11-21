from typing import (Any, Dict, List, NewType, TypedDict, Mapping, Union, Iterable, Callable, Type)
from .messages import (WebsocketFilterMessage, WebsocketMessage)

Hash32 = NewType('Hash32', bytes)
HexAddress = NewType('HexAddress', str)
ChecksumAddress = NewType('ChecksumAddress', HexAddress)

EventData = TypedDict(
    'EventData', {
        'args': Dict[str, Any],
        'event': str,
        'logIndex': int,
        'transactionIndex': int,
        'transactionHash': Hash32,
        'address': ChecksumAddress,
        'blockHash': Hash32,
        'blockNumber': int,
    })

SchemaType = str
SchemaFormat = str
SchemaExtraction = Dict[Any, Any]

SchemaDef = TypedDict('SchemaDef', {
    'type': SchemaType,
    'format': SchemaFormat,
    'enum': Iterable[Any],
    'items': SchemaType,
    'srckey': Union[str, Callable[[Any], Any]],
}, total=False)

JSONSchema = TypedDict('JSONSchema', {'properties': Mapping[str, SchemaDef]}, total=False)


class ContractFilter():
    callbacks: List[Callable[..., Any]]
    stopped: bool
    poll_interval: float
    filter_id: int
    web3: Any

    def get_new_entries(self) -> List[EventData]:
        ...

    def get_all_entries(self) -> List[EventData]:
        ...


FormatClass = Type[WebsocketFilterMessage]
Message = WebsocketMessage
