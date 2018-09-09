from time import time as now
from enum import Enum
from misc.extended_json_codec import make_custom_serializable
import numpy as np
import io
from threading import Thread, Event
import json
import os
from misc.extended_json_codec import ExtendedJSONCodec
from safe_picamera import PiMotionAnalysis, PiVideoFrame, PiVideoFrameType
from specialized.camera_support.mux import MP4StreamMuxer


make_custom_serializable(PiVideoFrame)


@make_custom_serializable
class CamEventType(Enum):
    WRITE = 'write'
    FLUSH = 'flush'
    ANALYZE = 'analyze'


@make_custom_serializable
class CamEvent:
    def __init__(self, time, event_type, frame, data):
        self.time = time
        self.event_type = event_type
        self.frame = frame
        self.data = data

    def _encode_data(self):
        if self.event_type == CamEventType.ANALYZE:
            with io.BytesIO() as buffer:
                np.save(buffer, self.data)
                return buffer.getvalue()
        elif self.event_type == CamEventType.WRITE:
            return self.data
        elif self.event_type == CamEventType.FLUSH:
            return None

    @classmethod
    def _decode_data(cls, event_type, data):
        if event_type == CamEventType.ANALYZE:
            with io.BytesIO(data) as buffer:
                return np.load(buffer)
        elif event_type == CamEventType.WRITE:
            return data
        elif event_type == CamEventType.FLUSH:
            return None

    def to_json(self):
        return {'time': self.time, 'event_type': self.event_type.value, 'frame': self.frame,
                'data': self._encode_data()}

    @classmethod
    def from_json(cls, payload):
        event_type = CamEventType(payload['event_type'])
        return cls(payload['time'], event_type, payload['frame'], cls._decode_data(event_type, payload['data']))

    def __lt__(self, other):  # pragma: no cover
        return self.time < other.time

    def __le__(self, other):  # pragma: no cover
        return self.time <= other.time

    def __gt__(self, other):  # pragma: no cover
        return self.time > other.time

    def __ge__(self, other):  # pragma: no cover
        return self.time >= other.time

    def __eq__(self, other):  # pragma: no cover
        if self.time != other.time or self.event_type != other.event_type:
            return False
        # Smart compare data
        if isinstance(self.data, np.ndarray) and isinstance(other.data, np.ndarray):
            return np.all(self.data == other.data)
        return self.data == other.data

    def __ne__(self, other):  # pragma: no cover
        return not self.__eq__(other)


class Recorder:  # pragma: no cover
    def record_event(self, event_type, data=None):
        self.events.append(CamEvent(now() - self.start_time, event_type, self.camera.frame, data))

    @property
    def events(self):
        return self.data['events']

    def __init__(self, camera):
        self.start_time = now()
        self.camera = camera
        self.data = dict(framerate=int(self.camera.framerate), resolution=list(self.camera.resolution), events=[])


class MotionRecorder(PiMotionAnalysis):  # pragma: no cover
    def analyze(self, array):
        self._recorder.record_event(CamEventType.ANALYZE, array)

    def __init__(self, recorder):
        super(MotionRecorder, self).__init__(recorder.camera)
        self._recorder = recorder


class VideoRecorder:  # pragma: no cover
    def write(self, data):
        self._recorder.record_event(CamEventType.WRITE, data)
        self._muxer.append(data, self._recorder.camera.frame.frame_type == PiVideoFrameType.sps_header,
                           self._recorder.camera.frame.complete)

    def flush(self):
        self._recorder.record_event(CamEventType.FLUSH)
        self._muxer.end(self._recorder.camera.framerate, self._recorder.camera.resolution)

    def dump_mp4(self, fp):
        fp.write(self._muxer.stream.getvalue())

    def __init__(self, recorder):
        self._recorder = recorder
        self._muxer = MP4StreamMuxer(io.BytesIO())
        self._muxer.begin()


PiMotionAnalysisMockup = PiMotionAnalysis


class PiCameraMockup:  # pragma: no cover
    def __init__(self):
        self._recording = False
        self._bitrate = 7500
        self._framerate = 10
        self._resolution = (320, 240)
        self._output = None
        self._motion_output = None
        self._frame = PiVideoFrame(index=0, frame_type=None, frame_size=0, video_size=0, split_size=0, timestamp=0,
                                   complete=False)

    @property
    def resolution(self):
        return self._resolution

    @resolution.setter
    def resolution(self, value):
        self._resolution = value

    @property
    def framerate(self):
        return self._framerate

    @framerate.setter
    def framerate(self, value):
        self._framerate = value

    @property
    def bitrate(self):
        return self._bitrate

    @bitrate.setter
    def bitrate(self, value):
        self._bitrate = value

    @property
    def frame(self):
        return self._frame

    @property
    def recording(self):
        return self._recording

    def mock_event(self, event):
        self._frame = event.frame
        if event.event_type is CamEventType.WRITE and self._output is not None:
            self._output.write(event.data)
        elif event.event_type is CamEventType.FLUSH and self._output is not None:
            self._output.flush()
        elif event.event_type is CamEventType.ANALYZE and self._motion_output is not None:
            self._motion_output.analyze(event.data)

    def start_recording(self, output, format='h264', resize=None, splitter_port=1, motion_output=None, **_):
        assert resize is None, 'Unsupported'
        assert format == 'h264', 'Unsupported'
        assert splitter_port == 1, 'Unsupported'
        self._output = output
        self._motion_output = motion_output
        self._recording = True

    def start_preview(self, *_, **__):
        pass

    def stop_recording(self):
        self._recording = False

    def request_key_frame(self):
        pass


class PiCameraReplay:
    DEFAULT_TIME_FACTOR = 1.

    def __init__(self, replay_data, camera=PiCameraMockup()):
        # Partial copy
        self._camera = camera
        self._camera.resolution = replay_data.get('resolution', (320, 240))
        self._camera.framerate = replay_data.get('framerate', 10)
        self._events = sorted([CamEvent(e.time, e.event_type, e.frame, e.data) for e in replay_data.get('events', [])])
        if len(self._events) == 0:  # pragma: no cover
            raise ValueError('You must provide at least one event')
        self._replay_thread = None
        self._stop_event = Event()
        self._replace_time_with_wait_time()
        self._has_stopped = Event()
        self._time_factor = 1.
        self.time_factor = self.__class__.DEFAULT_TIME_FACTOR

    def _replace_time_with_wait_time(self):
        for i in range(len(self._events) - 1, 0, -1):
            self._events[i].time -= self._events[i - 1].time

    def _replay(self):
        # In a scale from 1 to 10, this scores "dumbest".
        # But should do the job
        def _wait(amount):
            start_t = now()
            while now() - start_t < amount:
                if self._stop_event.wait(0.01):
                    return False
            return not self._stop_event.is_set()
        evt_idx = 0
        while evt_idx < len(self._events) and _wait(self._events[evt_idx].time / self.time_factor):
            if self._camera.recording:
                self._camera.mock_event(self._events[evt_idx])
                evt_idx += 1
        self._has_stopped.set()

    @property
    def time_factor(self):
        return self._time_factor

    @time_factor.setter
    def time_factor(self, value):
        self._time_factor = max(0.01, value)

    @property
    def camera(self):
        return self._camera

    @property
    def has_stopped(self):
        return self._has_stopped

    def replay(self):
        if self._has_stopped.is_set():
            self._stop_event.clear()
            self._has_stopped.clear()
            self._replay_thread = Thread(target=self._replay)
            self._replay_thread.start()

    def __enter__(self):
        self._has_stopped.set()
        self.replay()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        self._replay_thread.join()


def load_demo_events():
    with open(os.path.join(os.path.dirname(__file__), 'cam_demo.json')) as fp:
        return json.load(fp, object_hook=ExtendedJSONCodec.hook)
