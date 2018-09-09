from datetime import datetime
from json import JSONEncoder
from json.encoder import encode_basestring_ascii, encode_basestring, INFINITY, _make_iterencode
from enum import Enum
from base64 import b64encode, b64decode


def _is_namedtuple(typ):
    return issubclass(typ, tuple) and \
           getattr(typ, '_fields', None) is not None


def make_custom_serializable(typ):
    has_custom_serialize = callable(getattr(typ, 'to_json', None))
    has_custom_deserialize = callable(getattr(typ, 'from_json', None))
    if has_custom_deserialize != has_custom_serialize:
        raise RuntimeError('Serializable classes that define one of the from_json, to_json methods must define also '
                           'the other.')
    elif not has_custom_serialize and not has_custom_deserialize:
        # Synthesize methods for known types
        if issubclass(typ, Enum):
            typ.to_json = lambda self: self.value
            typ.from_json = classmethod(lambda cls, payload: cls(payload))
        elif _is_namedtuple(typ):
            typ.to_json = lambda self: dict({k: getattr(self, k) for k in typ._fields})
            typ.from_json = classmethod(lambda cls, payload: cls(**{k: v for k, v in payload.items() if
                                                                    k in typ._fields}))
        else:
            def typ_from_json(cls, payload):
                obj = cls()
                obj.__dict__.update(payload)
                return obj
            typ.from_json = classmethod(typ_from_json)
            typ.to_json = lambda self: self.__dict__
    ExtendedJSONCodec.ACCEPTED_CLASSES[typ.__name__] = typ
    return typ


class ExtendedJSONCodec(JSONEncoder):
    ACCEPTED_CLASSES = {}
    TYPE_KEY = '__type'

    @classmethod
    def _can_be_custom_serialized(cls, obj):
        return obj.__class__ in cls.ACCEPTED_CLASSES.values() and callable(getattr(obj, 'to_json'))

    @classmethod
    def _can_be_custom_deserialized(cls, payload):
        return callable(getattr(cls.ACCEPTED_CLASSES.get(payload.get(cls.TYPE_KEY)), 'from_json', None))

    @classmethod
    def _isinstance(cls, obj, is_cls):
        if obj.__class__ in cls.ACCEPTED_CLASSES.values():
            return False
        return isinstance(obj, is_cls)

    def iterencode(self, o, _one_shot=False):  # pragma: no cover
        """Encode the given object and yield each string
        representation as available.

        For example::

            for chunk in JSONEncoder().iterencode(bigobject):
                mysocket.write(chunk)

        This method is identical to json.JSONEncoder.iterencode, except that one shot is ignored.
        """
        if self.check_circular:
            markers = {}
        else:
            markers = None
        if self.ensure_ascii:
            _encoder = encode_basestring_ascii
        else:
            _encoder = encode_basestring

        def floatstr(oo, allow_nan=self.allow_nan,
                     _repr=float.__repr__, _inf=INFINITY, _neginf=-INFINITY):
            # Check for specials.  Note that this type of test is processor
            # and/or platform-specific, so do tests which don't depend on the
            # internals.

            if oo != oo:
                text = 'NaN'
            elif oo == _inf:
                text = 'Infinity'
            elif oo == _neginf:
                text = '-Infinity'
            else:
                return _repr(oo)

            if not allow_nan:
                raise ValueError(
                    "Out of range float values are not JSON compliant: " +
                    repr(o))

            return text

        # Force using _make_iterencode with custom isinstance fn
        _iterencode = _make_iterencode(
            markers, self.default, _encoder, self.indent, floatstr,
            self.key_separator, self.item_separator, self.sort_keys,
            self.skipkeys, False, isinstance=self.__class__._isinstance)
        return _iterencode(o, 0)

    def default(self, obj):
        if isinstance(obj, datetime):
            return {self.__class__.TYPE_KEY: obj.__class__.__name__, obj.__class__.__name__: obj.timestamp()}
        elif isinstance(obj, bytes):
            return {self.__class__.TYPE_KEY: obj.__class__.__name__, obj.__class__.__name__: b64encode(obj).decode()}
        elif self.__class__._can_be_custom_serialized(obj):
            return {self.__class__.TYPE_KEY: obj.__class__.__name__, obj.__class__.__name__: obj.to_json()}
        else:
            return JSONEncoder.default(self, obj)

    @classmethod
    def hook(cls, payload):
        declared_type = payload.get(cls.TYPE_KEY)
        # Manually add support for bytes and datetime
        if declared_type == datetime.__name__:
            return datetime.fromtimestamp(payload.get(datetime.__name__))
        elif declared_type == bytes.__name__:
            return b64decode(payload.get(bytes.__name__).encode())
        elif cls._can_be_custom_deserialized(payload):
            declared_type = cls.ACCEPTED_CLASSES[payload.get(cls.TYPE_KEY)]
            return declared_type.from_json(payload.get(declared_type.__name__))
        else:
            return payload
