from . import json_schema, messages

if __name__ == "__main__":
    import doctest
    doctest.testmod(m=messages)
    doctest.testmod(m=json_schema)
