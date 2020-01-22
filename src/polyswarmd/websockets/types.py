import functools
from string import hexdigits
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    TypeVar,
)
import uuid

from pydantic import Field, PositiveInt, constr
from pydantic.validators import str_validator

from polyswarmartifact import ArtifactType as _ArtifactType

V = TypeVar('V')

# mypy doesn't allow the use of TypeVar as a type
TypeVarType = Any

# The string distinguishing one event message from another
EventId = str
# Distinguish between ordinary ints and Uin256, even if they share the same fundamental
Uint256 = PositiveInt
# Result of `safe_int_to_bool_list`
BoolVector = List[bool]
# allow +2 for '0x', although we should be getting HexBytes anyway
TXID = constr(min_length=64, max_length=66)

MessageField = functools.partial(Field, None)
BountyGuid = MessageField(alias='bountyGuid')
From = MessageField(alias='from')
To = MessageField(alias='to')


class EventData(Mapping):
    """Event data returned from web3 filter requests"""
    args: Dict[str, Any]
    event: str
    logIndex: int
    transactionIndex: int
    transactionHash: bytes
    address: str
    blockHash: bytes
    blockNumber: int


class EventGUID(str):
    """An integer-derived GUID field"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, int):
            raise ValueError("Expected an integer-coded GUID")
        return cls(str(uuid.UUID(int=int(v))))


class ArtifactTypeField(str):
    """The type for `ArtifactType`"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, int):
            return cls(_ArtifactType.to_string(_ArtifactType(v)))
        elif isinstance(v, str):
            return cls(v)
        else:
            raise ValueError(f"Could not build an ArtifactType from value provided: {v}")


class EthereumAddress(str):
    """A hex-coded 40-byte ethereum address, with or without the '0x' prefix"""

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate_address

    @classmethod
    def validate_address(cls, v):
        hdigits = v
        if v.startswith('0x'):
            hdigits = v[2:]
        else:
            v = '0x' + v
        if len(hdigits) != 40 or any(ch not in hexdigits for ch in hdigits):
            raise ValueError("Expected an 40-bit hex value")
        return cls(v)


class ArtifactMetadata(Dict, Generic[V]):
    _metadata_validator: ClassVar[V]
    _substitute_metadata: ClassVar[Optional[Callable[[str, Callable], Any]]]

    @classmethod
    def __get_validators__(cls):
        yield str_validator
        yield cls.validate

    @classmethod
    def validate(cls, uri):
        if not cls._metadata_validator:
            raise ValueError("No _metadata_validator")
        return ArtifactMetadata.substitute(cls, uri)

    @classmethod
    def __class_getitem__(cls, typ):
        return type(
            f'ArtifactMetadata_{typ.__name__}', ArtifactMetadata.__bases__, {
                **ArtifactMetadata.__dict__, '_metadata_validator': typ.validate
            }
        )

    @staticmethod
    def build_substitute_metadata():
        from polyswarmd.app import app
        from polyswarmd.views.bounties import substitute_metadata
        from requests_futures.sessions import FuturesSession
        config: Optional[Dict[str, Any]] = app.config

        def partial_substitute(uri, validate):
            return substitute_metadata(
                uri,
                config['POLYSWARMD'].artifact.client,
                FuturesSession(adapter_kwargs={'max_retries': 3}),
                validate=validate,
                redis=config['POLYSWARMD'].redis.client
            )

        return partial_substitute

    @staticmethod
    def substitute(cls, uri):
        """Create & assign a new implementation of _substitute_metadata"""
        if not ArtifactMetadata._substitute_metadata:
            ArtifactMetadata._substitute_metadata = cls.build_substitute_metadata()
        return ArtifactMetadata._substitute_metadata(uri, cls._metadata_validator)
