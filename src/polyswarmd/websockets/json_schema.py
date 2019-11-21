import uuid
import operator
from functools import partial
from typing import Any, Callable, Dict, cast
from ._types import JSONSchema, SchemaExtraction


def compose(f, g):
    return lambda x: f(g(x))


class PSJSONSchema():
    schema: JSONSchema
    _extractor: Dict[str, Callable[[Any], Any]]

    _TYPES = {'string': str, 'integer': int, 'number': float, 'bool': bool, 'boolean': bool, 'array': list}

    _FORMATTERS = {'uuid': lambda x: uuid.UUID(int=x), 'ethaddr': str}

    def __init__(self, schema: Dict[str, Any]):
        self.schema = cast(JSONSchema, schema)
        self._extractor = self.build_extractor()

    def visitor(self):
        yield from self.schema.get('properties', {})

    def extract(self, instance: Any) -> SchemaExtraction:
        """Extract and format fields from a source `instance` object

        This uses ordinary jsonschema manifests, with the addition of polyswarm-specific keys:

            srckey: str - Get the field with the same name from `instance`
            srckey: callable - Run this function with `instance` as an argument

        If srckey is not present at all, it attempts to fetch the value from `source`
        with the same name/key as the definition.

        >>> make_range = lambda src: src['range']()
        >>> schema = PSJSONSchema({ \
            'properties': { \
                'a': {'type':'string'},  \
                'b': {'type':'string', 'srckey': 'b_src'}, \
                'c': {'type':'string', 'srckey': 'c_src'}, \
                'x': {'type':'integer'}, \
                'fetch': {'type': 'array', 'items': 'string', 'srckey': make_range}, \
                'xs': {'type': 'array', 'items': 'integer' }}})
        >>> instance = { 'a': "1", 'b_src': "2", 'c_src': 3, 'x': 4, \
                        'xs': ["5","6"], 'range': lambda: range(1,3) }
        >>> schema.extract(instance)
        {'a': '1', 'b': '2', 'c': '3', 'x': 4, 'fetch': ['1', '2'], 'xs': [5, 6]}
        """
        return {k: fn(instance) for k, fn in self._extractor.items()}

    @classmethod
    def map_type(cls, name):
        return cls._TYPES[name]

    def build_extractor(self):
        "Return a dictionary of functions which each extract/format a def_name"
        extract_map = {}
        # This code works by mapping each formatting-task to a particular function and then applying
        # them in series, e.g
        #  {'type': 'uuid', 'srckey': 'SRC', 'format': 'uuid' }
        # would be converted into (using the _TYPES and _FORMATTERS tables above)
        #   str(uuid.UUID(int=operator.itemgetter('SRC')))
        for def_name, def_schema in self.visitor():
            # You may use a string to indicate where to look in the source map,
            # and if none is provided, it will use the key/def_name by default
            srckey = def_schema.get('srckey', def_name)
            if type(srckey) is str:
                extract_fn = operator.itemgetter(srckey)
            elif callable(srckey):
                extract_fn = srckey

            fmt = def_schema.get('format')
            if fmt:
                extract_fn = compose(self._FORMATTERS[fmt], extract_fn)

            itype = def_schema.get('items')
            if itype:
                extract_fn = compose(partial(map, self.map_type(itype)), extract_fn)

            extract_fn = compose(self.map_type(def_schema['type']), extract_fn)
            extract_map[def_name] = extract_fn

        return extract_map

    def build_annotations(self):
        for name, schema in self.visitor():
            yield {name: self.map_type(schema['type'])}


if __name__ == "__main__":
    import doctest
    doctest.testmod()
