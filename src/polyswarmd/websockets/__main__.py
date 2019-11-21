
if __name__ == "__main__":
    import doctest
    from . import messages, json_schema
    doctest.testmod(m=messages)
    doctest.testmod(m=json_schema)
