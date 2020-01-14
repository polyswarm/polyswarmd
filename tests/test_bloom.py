import itertools
import pytest
import os
import random

from polyswarmd.utils.bloom import BloomFilter


@pytest.fixture
def log_entries():
    def _mk_address():
        return os.urandom(20)

    def _mk_topic():
        return os.urandom(32)
    return [
        (_mk_address(), [_mk_topic() for _ in range(1, random.randint(0, 4))])
        for _ in range(1, random.randint(0, 30))
    ]


def check_bloom(bloom, log_entries):
    for address, topics in log_entries:
        assert address in bloom
        for topic in topics:
            assert topic in bloom


def test_bloom_filter_add_method(log_entries):
    bloom = BloomFilter()

    for address, topics in log_entries:
        bloom.add(address)
        for topic in topics:
            bloom.add(topic)

    check_bloom(bloom, log_entries)


def test_bloom_filter_extend_method(log_entries):
    bloom = BloomFilter()

    for address, topics in log_entries:
        bloom.extend([address])
        bloom.extend(topics)

    check_bloom(bloom, log_entries)


def test_bloom_filter_from_iterable_method(log_entries):
    bloomables = itertools.chain.from_iterable(
        itertools.chain([address], topics) for address, topics in log_entries
    )
    bloom = BloomFilter.from_iterable(bloomables)
    check_bloom(bloom, log_entries)


def test_casting_to_integer():
    bloom = BloomFilter()

    assert int(bloom) == 0

    bloom.add(b'value 1')
    bloom.add(b'value 2')
    assert int(bloom) == int(
        '63119152483043774890037882090529841075600744123634985501563996'
        '49538536948165624479433922134690234594539820621615046612478986'
        '72305890903532059401028759565544372404512800814146245947429340'
        '89705729059810916441565944632818634262808769353435407547341248'
        '57159120012171916234314838712163868338766358254974260070831608'
        '96074485863379577454706818623806701090478504217358337630954958'
        '46332941618897428599499176135798020580888127915804442383594765'
        '16518489513817430952759084240442967521334544396984240160630545'
        '50638819052173088777264795248455896326763883458932483359201374'
        '72931724136975431250270748464358029482656627802817691648'
    )


def test_casting_to_binary():
    bloom = BloomFilter()

    assert bin(bloom) == '0b0'

    bloom.add(b'value 1')
    bloom.add(b'value 2')
    assert bin(bloom) == (
        '0b1000000000000000000000000000000000000000001000000100000000000000'
        '000000000000000000000000000000000000000000000010000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000001000000'
        '000000000000000000000000000000000000000000000000000000000000000010'
        '000000000000000000000000000000000000000100000000000000000000001000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000010000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000010000000000001000000000000001000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000001000000000000000000000000000000000000000000000000000100000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000000000000000000000'
        '000000000000000000000000000000000000000000000000100000000000000000'
        '00000000000000000000000000000000000001000000000000000000000000'
    )


def test_combining_filters():
    b1 = BloomFilter()
    b2 = BloomFilter()

    b1.add(b'a')
    b1.add(b'b')
    b1.add(b'c')

    b2.add(b'd')
    b2.add(b'e')
    b2.add(b'f')

    b1.add(b'common')
    b2.add(b'common')

    assert b'a' in b1
    assert b'b' in b1
    assert b'c' in b1

    assert b'a' not in b2
    assert b'b' not in b2
    assert b'c' not in b2

    assert b'd' in b2
    assert b'e' in b2
    assert b'f' in b2

    assert b'd' not in b1
    assert b'e' not in b1
    assert b'f' not in b1

    assert b'common' in b1
    assert b'common' in b2

    b3 = b1 | b2

    assert b'a' in b3
    assert b'b' in b3
    assert b'c' in b3
    assert b'd' in b3
    assert b'e' in b3
    assert b'f' in b3
    assert b'common' in b3

    b4 = b1 + b2

    assert b'a' in b4
    assert b'b' in b4
    assert b'c' in b4
    assert b'd' in b4
    assert b'e' in b4
    assert b'f' in b4
    assert b'common' in b4

    b5 = BloomFilter(int(b1))
    b5 |= b2

    assert b'a' in b5
    assert b'b' in b5
    assert b'c' in b5
    assert b'd' in b5
    assert b'e' in b5
    assert b'f' in b5
    assert b'common' in b5

    b6 = BloomFilter(int(b1))
    b6 += b2

    assert b'a' in b6
    assert b'b' in b6
    assert b'c' in b6
    assert b'd' in b6
    assert b'e' in b6
    assert b'f' in b6
    assert b'common' in b6
