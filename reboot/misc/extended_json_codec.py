from datetime import datetime
from json import JSONEncoder
from enum import Enum


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
        else:
            def typ_from_json(cls, payload):
                obj = cls()
                obj.__dict__.update(payload)
                return obj
            typ.from_json = classmethod(typ_from_json)
            typ.to_json = lambda self: self.__dict__
    ExtendedJSONCodec.ACCEPTED_CLASSES[typ.__name__] = typ


class ExtendedJSONCodec(JSONEncoder):
    ACCEPTED_CLASSES = {}
    TYPE_KEY = '__type'

    @classmethod
    def _can_be_custom_serialized(cls, obj):
        return obj.__class__ in cls.ACCEPTED_CLASSES.values() and callable(getattr(obj, 'to_json'))

    @classmethod
    def _can_be_custom_deserialized(cls, payload):
        return callable(getattr(cls.ACCEPTED_CLASSES.get(payload.get(cls.TYPE_KEY)), 'from_json', None))

    def default(self, obj):
        # Manually add support for bytes and datetime
        if isinstance(obj, datetime):
            return {self.__class__.TYPE_KEY: obj.__class__.__name__, obj.__class__.__name__: obj.timestamp()}
        elif isinstance(obj, bytes):
            return {self.__class__.TYPE_KEY: obj.__class__.__name__, obj.__class__.__name__: obj.hex()}
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
            return bytes.fromhex(payload.get(bytes.__name__))
        elif cls._can_be_custom_deserialized(payload):
            declared_type = cls.ACCEPTED_CLASSES[payload.get(cls.TYPE_KEY)]
            return declared_type.from_json(payload.get(declared_type.__name__))
        else:
            return payload
