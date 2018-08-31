import unittest
from enum import Enum
from misc.extended_json_codec import make_custom_serializable, ExtendedJSONCodec
import json
from datetime import datetime
from misc.dotdict import DotDict
from misc.cam_replay import CamEventType, CamEvent, PicameraReplay, PiMotionAnalysisMockup
import numpy as np
import io


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

    def test_nonserializable(self):
        class Something:
            pass
        with self.assertRaises(TypeError):
            through_json(Something())
        with self.assertRaises(RuntimeError):
            @make_custom_serializable
            class SomethingNonSerializable:
                @classmethod
                def from_json(cls, payload):  # pragma: no cover
                    pass
            # Dummy usage
            SomethingNonSerializable()  # pragma: no cover


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


class VideoEventCollector:
    def __init__(self, events):
        self._events = events

    def write(self, _):
        self._events.append(CamEventType.WRITE)

    def flush(self):
        self._events.append(CamEventType.FLUSH)


class MotionEventCollector(PiMotionAnalysisMockup):
    def __init__(self, events):
        super(MotionEventCollector, self).__init__(None)
        self._events = events

    def analyze(self, _):
        self._events.append(CamEventType.ANALYZE)


class TestPicameraReplay(unittest.TestCase):
    def test_replay(self):
        events = [
            CamEvent(0.0, CamEventType.WRITE, None),
            CamEvent(0.25, CamEventType.ANALYZE, None),
            CamEvent(0.5, CamEventType.FLUSH, None),
        ]
        collected_evt_types = []
        with PicameraReplay(events) as sim:
            sim.camera.start_recording(VideoEventCollector(collected_evt_types),
                                       motion_output=MotionEventCollector(collected_evt_types))
            sim.has_stopped.wait()
        self.assertEqual(len(collected_evt_types), 3)
        for i in range(0, len(events)):
            self.assertEqual(events[i].event_type, collected_evt_types[i])

    def test_abort_replay(self):
        events = [
            CamEvent(0.1, CamEventType.WRITE, None),
            CamEvent(0.25, CamEventType.ANALYZE, None),
            CamEvent(0.5, CamEventType.FLUSH, None),
        ]
        collected_evt_types = []
        with PicameraReplay(events):
            pass
        self.assertEqual(len(collected_evt_types), 0)

    def test_zero_wait_time(self):
        events = [
            CamEvent(0, CamEventType.WRITE, None)
        ]
        collected_evt_types = []
        with PicameraReplay(events):
            pass
        self.assertEqual(len(collected_evt_types), 0)

    def test_event_json(self):
        events = [
            CamEvent(0.1, CamEventType.WRITE, b'hellow'),
            CamEvent(0.25, CamEventType.ANALYZE, np.array([(0, 0, 0), (0, 0, 0), (0, 0, 0)],
                                                          dtype=[('x', '|i1'), ('y', '|i1'), ('sad', '<u2')])),
            CamEvent(0.5, CamEventType.FLUSH, None)
        ]
        events_copy = through_json(events)
        self.assertEqual(events, events_copy)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
