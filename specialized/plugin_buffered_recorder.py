from plugins.base import Process
from specialized.plugin_picamera import PiCameraProcessBase
from plugins.decorators import make_plugin
from specialized.camera_support.mux import DualBufferedMP4
from specialized.plugin_media_manager import MEDIA_MANAGER_PLUGIN_NAME
from plugins.processes_host import find_plugin
from Pyro4 import expose as pyro_expose
import logging
from misc.logging import ensure_logging_setup, camel_to_snake
from datetime import datetime
from misc.settings import SETTINGS
from safe_picamera import PiVideoFrameType
from threading import Lock
import math
from specialized.plugin_status_led import Status


BUFFERED_RECORDER_PLUGIN_NAME = 'BufferedRecorder'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(BUFFERED_RECORDER_PLUGIN_NAME))


@make_plugin(BUFFERED_RECORDER_PLUGIN_NAME, Process.CAMERA)
class BufferedRecorderPlugin(PiCameraProcessBase):
    def __init__(self):
        super(BufferedRecorderPlugin, self).__init__()
        self._last_sps_header_stamp = 0
        self._recorder = DualBufferedMP4()
        self._record_user_info = None
        self._is_recording = False
        self._keep_media = True
        self._flush_lock = Lock()
        self._has_just_flushed = False
        self._buffer_max_age = None
        self._sps_header_max_age = None
        self._footage_max_age = None
        self._record_status = None
        self._record_status_lock = Lock()

    def __enter__(self):
        super(BufferedRecorderPlugin, self).__enter__()
        self._has_just_flushed = True
        self._recorder.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._recorder.__exit__(exc_type, exc_val, exc_tb)
        super(BufferedRecorderPlugin, self).__exit__(exc_type, exc_val, exc_tb)

    def _set_recording_status(self, value):
        with self._record_status_lock:
            if value and self._record_status is None:
                self._record_status = Status.pulse((1, 0, 0))
            elif not value and self._record_status is not None:
                self._record_status.cancel()
                self._record_status = None

    @pyro_expose
    @property
    def footage_age(self):
        return self._recorder.footage_age

    @pyro_expose
    @property
    def buffer_age(self):
        return self._recorder.buffer_age

    @pyro_expose
    @property
    def total_age(self):
        return self._recorder.total_age

    @pyro_expose
    @property
    def footage_max_age(self):
        return self._footage_max_age

    @property
    def _camera(self):
        return self.root_picamera_plugin.camera

    @property
    def _last_frame(self):
        return self._camera.frame

    @pyro_expose
    @property
    def buffer_max_age(self):
        if self._buffer_max_age is None:
            # Lazily load this value, because we must be sure that a camera is instantiated
            self._buffer_max_age = 2 * self._camera.framerate * \
                                   SETTINGS.camera.get('buffer', cast_to_type=float, default=2.0, ge=1.0)
        return self._buffer_max_age

    @pyro_expose
    @buffer_max_age.setter
    def buffer_max_age(self, value):
        self._buffer_max_age = max(self._camera.framerate * 0.5, 1, value)

    @pyro_expose
    @property
    def sps_header_max_age(self):
        if self._sps_header_max_age is None:
            # Lazily load this value, because we must be sure that a camera is instantiated
            self._sps_header_max_age = self._camera.framerate * SETTINGS.camera.get(
                'clip_length_tolerance', cast_to_type=float, default=1.0, ge=1.0)
        return self._sps_header_max_age

    @pyro_expose
    @sps_header_max_age.setter
    def sps_header_max_age(self, value):
        self._sps_header_max_age = max(self._camera.framerate * 0.5, 1, value)

    @property
    def _last_sps_header_age(self):
        return self._recorder.total_age - self._last_sps_header_stamp

    def _handle_split_point(self):
        if self.footage_max_age is not None and self.footage_age >= self.footage_max_age:
            self._stop_and(True, handle_split_point_if_flushed=False)
            self._footage_max_age = None
        if self._recorder.is_recording and not self._is_recording:
            # We requested stop, but we haven't reached a split point. Now we can really stop.
            if self._keep_media:
                media_mgr = find_plugin(MEDIA_MANAGER_PLUGIN_NAME, Process.CAMERA)
                if not media_mgr:
                    _log.error('No media manager is running on the CAMERA process.')
                    _log.info('Discarding media with info %s.', str(self._record_user_info))
                    self._recorder.stop_and_discard()
                else:
                    file_name = self._recorder.stop_and_finalize(self._camera.framerate, self._camera.resolution)
                    media = media_mgr.deliver_media(file_name, 'mp4', self._record_user_info)
                    _log.info('Media %s with info %s was delivered.', str(media.uuid), str(self._record_user_info))
            else:
                _log.info('Discarding media with info %s.', str(self._record_user_info))
                self._recorder.stop_and_discard()
            self._record_user_info = None
        if self._recorder.buffer_age > self.buffer_max_age:
            self._recorder.rewind_buffer()
        # Update the sps header age
        self._last_sps_header_stamp = self._recorder.total_age

    @pyro_expose
    def record(self, info=None, stop_after_seconds=None):
        _log.info('Requested media with info %s of maximum length %s.', str(info), str(stop_after_seconds))
        self._keep_media = True
        self._is_recording = True
        self._record_user_info = info
        if stop_after_seconds is not None:
            stop_after_seconds = float(stop_after_seconds)
            if stop_after_seconds < 0 or math.isinf(stop_after_seconds):
                self._footage_max_age = None
            else:
                self._footage_max_age = int(max(1., stop_after_seconds) * self._camera.framerate)
        self._set_recording_status(True)
        self._recorder.record()

    @pyro_expose
    @property
    def is_recording(self):
        return self._recorder.is_recording and self._is_recording

    @pyro_expose
    @property
    def is_finalizing(self):
        return self._recorder.is_recording and self._keep_media and not self._is_recording

    def _stop_and(self, finalize, handle_split_point_if_flushed=True):
        self._set_recording_status(False)
        self._is_recording = False
        self._keep_media = finalize
        if handle_split_point_if_flushed:
            with self._flush_lock:
                # This is the only other split point at which we are sure that an SPS will have to follow
                if self._has_just_flushed:
                    self._handle_split_point()

    @pyro_expose
    def stop_and_discard(self):
        self._stop_and(finalize=False)

    @pyro_expose
    def stop_and_finalize(self):
        self._stop_and(finalize=True)

    def write(self, data):
        with self._flush_lock:
            self._has_just_flushed = False
        # Update annotation
        self._camera.annotate_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # If it's a split point, one can stop
        if self._last_frame.frame_type == PiVideoFrameType.sps_header:
            self._handle_split_point()
            self._recorder.append(data, True, self._last_frame.complete)
        else:
            self._recorder.append(data, False, self._last_frame.complete)
        # Do we need to request a new sps_header
        if self._last_sps_header_age > min(self.sps_header_max_age, self.buffer_max_age):
            self._camera.request_key_frame()

    def flush(self):
        with self._flush_lock:
            self._has_just_flushed = True
            self._handle_split_point()
