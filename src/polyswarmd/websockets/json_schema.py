from functools import partial
import operator
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    List,
    Mapping,
    SupportsInt,
    Union,
    cast,
)
from typing_extensions import TypedDict
import uuid

SchemaType = str
SchemaFormat = str
SchemaExtraction = Dict[Any, Any]

SchemaDef = TypedDict(
    'SchemaDef', {
        'type': SchemaType,
        'format': SchemaFormat,
        'enum': Iterable[Any],
        'items': SchemaType,
        'srckey': Union[str, Callable[[str, Any], Any]],
    },
    total=False
)

JSONSchema = TypedDict('JSONSchema', {'properties': Mapping[str, SchemaDef]}, total=False)


def compose(f, g):
    """"Return a function which which composes/pipes g(x) into f(x)"""
    return lambda x: f(g(x))


def to_int_uuid(x: SupportsInt) -> uuid.UUID:
    """"Return an uuid from an int-able value"""
    return uuid.UUID(int=int(x))


class PSJSONSchema:
    """Extract and format fields from a source `instance` object

    This uses ordinary jsonschema manifests, with the addition of polyswarm-specific keys:

        srckey: str - Get the field with the same name from `instance`
        srckey: callable - Run this function with `instance` as an argument

    If srckey is not present at all, it attempts to fetch the value from `source`
    with the same name/key as the definition.

    >>> make_range = lambda key, src: range(1, src[key])
    >>> schema = PSJSONSchema({
    ... 'properties': {
    ...     'a': {'type':'string'},
    ...     'b': {'type':'string', 'srckey': 'b_src'},
    ...     'c': {'type':'string', 'srckey': 'c_src'},
    ...     'x': {'type':'integer'},
    ...     'range': {'type': 'array', 'items': 'string', 'srckey': make_range},
    ...     'xs': {'type': 'array', 'items': 'integer' }}})
    >>> instance = { 'a': "1", 'b_src': "2", 'c_src': 3, 'x': 4, 'xs': ["5","6"], 'range': 3 }
    >>> schema.extract(instance)
    {'a': '1', 'b': '2', 'c': '3', 'x': 4, 'range': ['1', '2'], 'xs': [5, 6]}
    """
    _TYPES: ClassVar[Dict[str, Callable[[Any], Any]]] = {
        'string': str,
        'integer': int,
        'number': float,
        'boolean': bool,
        'array': list
    }
    _FORMATTERS: ClassVar[Dict[str, Callable[[Any], Any]]] = {'uuid': to_int_uuid}

    schema: JSONSchema
    _extractor: Dict[str, Callable[[Any], Any]]

    def __init__(self, schema: Dict[str, Any]):
        self.schema = cast(JSONSchema, schema)
        self._extractor = self.build_extractor()

    def visitor(self):
        yield from self.schema.get('properties', {}).items()

    def extract(self, instance: Any) -> SchemaExtraction:
        return {k: fn(instance) for k, fn in self._extractor.items()}

    def build_extractor(self):
        """Return a dictionary of functions which each extract/format a def_name"""
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
                extract_fn = partial(srckey, def_name)

            fmt = def_schema.get('format')
            if fmt and fmt in self._FORMATTERS:
                extract_fn = compose(self._FORMATTERS[fmt], extract_fn)

            itype = def_schema.get('items')
            if itype:
                extract_fn = compose(partial(map, self._TYPES[itype]), extract_fn)

            dtype = def_schema.get('type')
            if dtype:
                extract_fn = compose(self._TYPES[dtype], extract_fn)
            extract_map[def_name] = extract_fn

        return extract_map

    def build_annotations(self):
        """Return a mypy function annotation for this schema

        This is used by gen_stubs.py, not in application logic"""
        annotations = {}
        for name, schema in self.visitor():
            type_name = schema.get('type')
            if type_name:
                if type_name == 'array':
                    elt = List[self._TYPES.get(schema.get('items'), Any)]  # type: ignore
                else:
                    elt = self._TYPES.get(type_name, Any)

                try:
                    annotations[name] = f'zv.{elt.__name__}'
                except (NameError, LookupError, AttributeError):
                    annotations[name] = elt
            else:
                annotations[name] = Any  # type: ignore
        return annotations
