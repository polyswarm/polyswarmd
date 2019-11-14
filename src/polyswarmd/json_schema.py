import uuid
from typing import Any, Dict

JSONSchema = Any


def copy_with_schema(schema: JSONSchema, source: Any) -> Dict[str, Any]:
    """Extract and format fields from a `source' object with jsonschema

    It extends jsonschema with several special keys that control extraction from `source`:

        $#fetch - Run a function with args=[source, key, property_schema]
        $#from - Extract this key from `source'

        $#convert - If present and True, format and convert the copied value

    If neither $#fetch or $#from are present, it attempts to fetch the value from `source`
    with the same name as the key.
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
            result[key] = _apply_conversion(_apply_format(value))(value, pschema)
        else:
            result[key] = value

    return result

_formatters = {'uuid': lambda x: uuid.UUID(int=x)}


def _apply_format(value: Any, schema: JSONSchema) -> Any:
    if 'format' in schema and schema['format'] in _formatters:
        return _formatters[schema['format']](value)
    return value


def _convert_array(xs: Iterable[Any], schema: JSONSchema):
    return [_apply_conversion(x, schema) for x in xs]


_conversions = {
    'string': str,
    'integer': int,
    'array': _convert_array,
    'number': float,
    'bool': bool,
}


def _apply_conversion(value: Any, schema: JSONSchema) -> Any:
    if 'type' in schema and schema['type'] in _conversions:
        return _conversions[schema['type']](value)
    elif 'items' in schema and schema['items'] in _conversions:
        return _conversions[schema['items']](value)
    return value
