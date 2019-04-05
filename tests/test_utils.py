import json
import pytest

from polyswarmd import utils, app
from polyswarmd.eth import ZERO_ADDRESS


def test_bool_list_to_int():
    bool_list = utils.bool_list_to_int([True, True, False, True])
    expected = 11
    assert bool_list == expected


def test_int_to_bool_list():
    bool_list = utils.int_to_bool_list(11)
    expected = [True, True, False, True]
    assert bool_list == expected


def test_safe_int_to_bool_list():
    bool_list = utils.safe_int_to_bool_list(0, 5)
    expected = [False, False, False, False, False]
    assert bool_list == expected
