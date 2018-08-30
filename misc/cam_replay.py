from picamera.array import PiMotionAnalysis
from time import time as now
from enum import Enum
from misc.extended_json_codec import make_custom_serializable
import numpy as np
import io
from base64 import b64encode as base64_encode, b64decode as base64_decode


@make_custom_serializable
class EventType(Enum):
    WRITE = 'write'
    FLUSH = 'flush'
    ANALYZE = 'analyze'


@make_custom_serializable
class Event:
    def __init__(self, time, event_type, data):
        self.time = time
        self.event_type = event_type
        self.data = data

    def _encode_data(self):
        if self.event_type == EventType.ANALYZE:
            with io.BytesIO() as buffer:
                np.save(buffer, self.data)
                return base64_encode(buffer.getvalue())
        elif self.event_type == EventType.WRITE:
            return self.data.hex()
        elif self.event_type == EventType.FLUSH:
            return None

    @classmethod
    def _decode_data(cls, event_type, data):
        if event_type == EventType.ANALYZE:
            with io.BytesIO(base64_decode(data)) as buffer:
                return np.load(buffer)
        elif event_type == EventType.WRITE:
            return bytes.fromhex(data)
        elif event_type == EventType.FLUSH:
            return None

    def to_json(self):
        return {'time': self.time, 'event_type': self.event_type.value, 'data': self._encode_data()}

    @classmethod
    def from_json(cls, payload):
        event_type = EventType(payload['event_type'])
        return cls(payload['time'], event_type, cls._decode_data(event_type, payload['data']))


class Recorder:
    def record_event(self, event_type, data=None):
        self.data.append(Event(now() - self.start_time, event_type, data))

    def __init__(self):
        self.start_time = now()
        self.data = []


class MotionRecorder(PiMotionAnalysis):
    def analyze(self, array):
        self._recorder.record_event(EventType.ANALYZE, array)

    def __init__(self, recorder, cam):
        super(MotionRecorder, self).__init__(cam)
        self._recorder = recorder


class VideoRecorder:
    def write(self, data):
        self._recorder.record_event(EventType.WRITE, data)

    def flush(self):
        self._recorder.record_event(EventType.FLUSH)

    def __init__(self, recorder):
        self._recorder = recorder
