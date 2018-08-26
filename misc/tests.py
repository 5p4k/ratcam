import unittest
from enum import Enum
from misc.extended_json_codec import make_custom_serializable, ExtendedJSONCodec
import json
from datetime import datetime
from misc.dotdict import DotDict


def through_json(obj):
    return json.loads(json.dumps(obj, cls=ExtendedJSONCodec), object_hook=ExtendedJSONCodec.hook)


class TestCustomSerialization(unittest.TestCase):
    def test_serialize_enum(self):
        @make_custom_serializable
        class TestEnum(Enum):
            FIRST = 1
            SECOND = 2
            ANY = 'any'
        self.assertIs(TestEnum.FIRST, through_json(TestEnum.FIRST))
        self.assertIs(TestEnum.SECOND, through_json(TestEnum.SECOND))
        self.assertIs(TestEnum.ANY, through_json(TestEnum.ANY))

    def test_serialize_dict(self):
        @make_custom_serializable
        class TestDict:
            def __init__(self, a=None, b=None):
                self.a = a
                self.b = b

            def __eq__(self, other):
                return self.a == other.a and self.b == other.b

        self.assertEqual(TestDict(), through_json(TestDict()))
        self.assertEqual(TestDict(a=1), through_json(TestDict(a=1)))
        self.assertEqual(TestDict(b=2), through_json(TestDict(b=2)))
        self.assertEqual(TestDict(a='foo', b='bar'), through_json(TestDict(a='foo', b='bar')))

    def test_serialize_builtins(self):
        now = datetime.now()
        self.assertEqual(now, through_json(now))
        self.assertEqual(b'hellow', through_json(b'hellow'))

    def test_serialize_custom(self):
        @make_custom_serializable
        class TestCustom:
            def __init__(self, a=None):
                self.a = a

            def __eq__(self, other):
                return self.a == other.a

            def to_json(self):
                return self.a

            @classmethod
            def from_json(cls, payload):
                return cls(payload)

        self.assertEqual(TestCustom(), through_json(TestCustom()))
        self.assertEqual(TestCustom(5), through_json(TestCustom(5)))
        self.assertEqual(TestCustom(b'foobar'), through_json(TestCustom(b'foobar')))


class TestDotDict(unittest.TestCase):
    def test_dotdict(self):
        d = DotDict({'a': {}})
        self.assertIsNotNone(d.a)
        self.assertIsInstance(d.a, DotDict)
        d.b = {'c': {}}
        self.assertIsNotNone(d.b)
        self.assertIsNotNone(d.b.c)
        self.assertIsInstance(d.b.c, DotDict)
        d = d.to_dict_tree()
        self.assertEqual(d, {'a': {}, 'b': {'c': {}}})


if __name__ == '__main__':
    unittest.main()
