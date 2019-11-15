import uuid
from typing import Any, Dict, Iterable

JSONSchema = Any


def copy_with_schema(schema: JSONSchema, source: Any) -> Dict[str, Any]:
    """Extract and format fields from a `source' object with jsonschema

    It extends jsonschema with several special keys that control extraction from `source`:

        $#fetch - Run a function with args=[source, key, property_schema]
        $#from - Extract this key from `source'

        $#convert - If present and True, format and convert the copied value

    If neither $#fetch or $#from are present, it attempts to fetch the value from `source`
    with the same name as the key.

    >>> make_range = lambda src, key, schema: src['range']()
    >>> schema = { \
        'properties': { \
            'a': {'type': 'string'},  \
            'b': {'type': 'string', '$#from': 'b_src'}, \
            'c': {'type': 'string', '$#from': 'c_src', '$#convert': True}, \
            'x': {'type': 'integer'}, \
            'fetch': { 'type': 'array', 'items': 'string', '$#convert': True, '$#fetch': make_range }, \
            'xs': { \
                'type': 'array', \
                'items': 'integer', \
                '$#convert': True }}}
    >>> source = { 'a': "1", 'b_src': "2", 'c_src': 3, 'x': 4, 'xs': ["5","6"], 'range': lambda: range(1,3) }
    >>> copy_with_schema(schema, source)
    {'a': '1', 'b': '2', 'c': '3', 'x': 4, 'fetch': ['1', '2'], 'xs': [5, 6]}
    """
    result = {}
    for key, pschema in schema['properties'].items():
        if '$#from' in pschema:
            value = source[pschema['$#from']]
        elif '$#fetch' in pschema:
            value = pschema['$#fetch'](source, key, pschema)
        elif key in source:
            value = source[key]
        else:
            AttributeError('Invalid JSONSchema extraction directive: ', key, schema)

        if pschema.get('$#convert'):
            result[key] = _apply_conversion(_apply_format(value, pschema), pschema)
        else:
            result[key] = value

    return result

_formatters = {'uuid': lambda x: uuid.UUID(int=x)}


def _apply_format(value: Any, schema: JSONSchema) -> Any:
    if 'format' in schema and schema['format'] in _formatters:
        return _formatters[schema['format']](value)
    return value


_conversions = {
    'string': str,
    'integer': int,
    'number': float,
    'bool': bool,
}


def _apply_conversion(value: Any, schema: JSONSchema) -> Any:
    dtype = schema.get('type')
    itype = schema.get('items')
    if dtype == 'array' and itype in _conversions:
        # this should really be recursive, but we're not using nested item definitions yet.
        return [ _conversions[itype](v) for v in value ]
    if dtype in _conversions:
        return _conversions[schema['type']](value)
    return value



if __name__ == "__main__":
    import doctest
    doctest.testmod()
