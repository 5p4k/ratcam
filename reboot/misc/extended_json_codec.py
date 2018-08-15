from datetime import datetime
from json import JSONEncoder


def make_custom_serializable(cls):
    ExtendedJSONCodec.ACCEPTED_CLASSES[cls.__name__] = cls


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
