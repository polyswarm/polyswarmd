# Based on eth-bloom (https://github.com/ethereum/eth-bloom, used under MIT
# license) with modifications
import logging
import numbers
import operator

from polyswarmd.utils import sha3

logger = logging.getLogger(__name__)

FILTER_BITS = 8 * 256
HASH_FUNCS = 8


def get_chunks_for_bloom(value_hash):
    assert HASH_FUNCS * 2 <= len(value_hash)
    for i in range(0, HASH_FUNCS):
        yield value_hash[2 * i:2 * (i+1)]  # noqa


def chunk_to_bloom_bits(chunk):
    assert FILTER_BITS <= (1 << 16)
    high, low = bytearray(chunk)
    return 1 << ((low + (high << 8)) & (FILTER_BITS - 1))


def get_bloom_bits(value):
    # Could decode the ipfs_hash and use it as is, but instead hash the
    # multihash representation to side-step different hash formats going
    # forward. Should rexamine this decision
    value_hash = sha3(value)
    for chunk in get_chunks_for_bloom(value_hash):
        bloom_bits = chunk_to_bloom_bits(chunk)
        yield bloom_bits


class BloomFilter(numbers.Number):
    value = None

    def __init__(self, value=0):
        self.value = value

    def __int__(self):
        return self.value

    def add(self, value):
        if not isinstance(value, bytes):
            raise TypeError("Value must be of type `bytes`")
        for bloom_bits in get_bloom_bits(value):
            self.value |= bloom_bits

    def extend(self, iterable):
        for value in iterable:
            self.add(value)

    @classmethod
    def from_iterable(cls, iterable):
        bloom = cls()
        bloom.extend(iterable)
        return bloom

    def __contains__(self, value):
        if not isinstance(value, bytes):
            raise TypeError("Value must be of type `bytes`")
        return all(self.value & bloom_bits for bloom_bits in get_bloom_bits(value))

    def __index__(self):
        return operator.index(self.value)

    def _combine(self, other):
        if not isinstance(other, (int, BloomFilter)):
            raise TypeError("The `or` operator is only supported for other `BloomFilter` instances")
        return BloomFilter(int(self) | int(other))

    def __hash__(self):
        return hash(self.value)

    def __or__(self, other):
        return self._combine(other)

    def __add__(self, other):
        return self._combine(other)

    def _icombine(self, other):
        if not isinstance(other, (int, BloomFilter)):
            raise TypeError("The `or` operator is only supported for other `BloomFilter` instances")
        self.value |= int(other)
        return self

    def __ior__(self, other):
        return self._icombine(other)

    def __iadd__(self, other):
        return self._icombine(other)