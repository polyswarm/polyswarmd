import pytest  # noqa


def pytest_generate_tests(metafunc):
    # This pytest hook that is called once for each test function It takes all of the dicts found in
    # `TestHeck`, selecting the key that shares the current test function's name & then
    # parameterizes by those as if they were arguments.
    name = metafunc.function.__name__
    metafunc.parametrize(['obj'], [[funcargs] for funcargs in metafunc.cls.params[name]])


GOOD = 'good'
BAD = 'bad'
F1 = 'first'
F2 = 'second'
F3 = 'third'
N1 = 'Alpha'
N2 = 'Beta'
N3 = 'Delta'
N4 = 'wut'


class TestHeck:
    params = {
        'test_equal_simple': [
            {GOOD: 1},
            {GOOD: lambda x: x == 1},
            {GOOD: lambda x: x},
            {GOOD: lambda x: True},
            {GOOD: lambda x: x}
        ],
        'test_equal_deep': [
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [3, 4]}}}},
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [3, lambda x: x == 4]}}}},
            {F1: {F2: {F3: {N1: 1, N2: lambda x: isinstance(x, str), N3: [3, 4]}}}},
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: lambda x: len(x) > 0}}}},
            {F1: {F2: {F3: {N1: lambda x: x == 1, N2: lambda x: isinstance(x, str), N3: [3, 4]}}}},
            {F1: {F2: {F3: {N1: lambda x: x == 1, N2: lambda x: isinstance(x, str), N3: lambda x: x[0] == 3}}}},
            {F1: {F2: {F3: lambda d: len(d.keys()) == 3}}}
        ],
        'test_not_equal_simple': [
            {BAD: lambda x: x > 1},
            {BAD: lambda x: x == float('nan')},
            {BAD: lambda x: x == -10123123},
            {BAD: lambda x: not x},
            {BAD: 2}
        ],
        'test_not_equal_deep': [
            {F1: {F2: {F3: {N1: 2, N2: 'two', N3: [3, 4]}}}},
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [4, 3]}}}},
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [4, lambda x: x != 3]}}}},
            {F1: {F2: {F3: {N1: 1, N2: lambda x: isinstance(x, int), N3: [3, 4]}}}},
            {F1: {F2: {F3: {N1: 1, N2: 'two', N3: lambda x: len(x) == 0}}}},
            {F1: {F2: {F3: {N1: lambda x: x == 1, N2: lambda x: isinstance(x, str), N3: [4, 3]}}}},
            {F1: {F2: {F3: {N1: lambda x: x == 2, N2: lambda x: isinstance(x, str), N3: [3, 4]}}}},
            {F1: {F2: {F3: lambda d: len(d.keys()) == 0}}},
            {F1: {F2: {F3: 1}}}
        ],
    }

    def test_equal_simple(self, obj, heck):
        assert {GOOD: 1} == heck(obj)

    def test_equal_deep(self, obj, heck):
        assert {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [3, 4]}}}} == heck(obj)

    def test_not_equal_simple(self, obj, heck):
        assert {BAD: 1} != heck(obj)

    def test_not_equal_deep(self, obj, heck):
        assert {F1: {F2: {F3: {N1: 1, N2: 'two', N3: [3, 4]}}}} != heck(obj)
