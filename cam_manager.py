#
# Copyright (C) 2017  Pietro Saccardi

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from picamera import PiCamera
from enum import Enum
from picamera.array import PiMotionAnalysis
from detector import DecayMotionDetector
from multiplex import DelayedMP4Recorder
from tempfile import NamedTemporaryFile
from misc import log


class EventType(Enum):
    VIDEO_READY = 'video'
    PHOTO_READY = 'photo'
    MOTION_DETECTED = 'moving'
    MOTION_STILL = 'still'


class MotionDetector(DecayMotionDetector, PiMotionAnalysis):
    def __init__(self, manager):
        DecayMotionDetector.__init__(self, manager.camera.resolution, int(manager.camera.framerate))
        PiMotionAnalysis.__init__(self, manager.camera)
        self.manager = manager

    def analyze(self, a):
        self.process_motion_vector(a)

    def _trigger_changed(self):
        self.manager.moving = self.is_triggered


class RecorderManager(DelayedMP4Recorder):
    def __init__(self, manager):
        super(RecorderManager, self).__init__(manager.camera, 2 * int(manager.camera.framerate))
        self.manager = manager

    def _mp4_ready(self, file_name):
        self.manager._report_event(EventType.VIDEO_READY, file_name)


class CameraManager:
    def __init__(self):
        self._camera = PiCamera()
        # Initialize default settings
        self._setup_camera()
        self._detector = MotionDetector(self)
        self._recorder = RecorderManager(self)
        self._manual_rec = False
        self._moving = False

    def __enter__(self):
        self._camera.start_recording(self._recorder, format='h264', motion_output=self._detector)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.camera.stop_recording()

    def _setup_camera(self):
        # self.camera.iso = 800
        # self.camera.sensor_mode = 3
        # self.camera.exposure_mode = 'night'
        self.camera.resolution = (1920, 1080)
        self.camera.framerate = 30

    @property
    def camera(self):
        return self._camera

    @property
    def manual_rec(self):
        return self._manual_rec

    @manual_rec.setter
    def manual_rec(self, value):
        self._manual_rec = value
        self._recorder.keep_recording = self._moving or self._manual_rec

    @property
    def moving(self):
        return self._moving

    @moving.setter
    def moving(self, value):
        # FIX
        self._moving = False
        self._recorder.keep_recording = self._moving or self._manual_rec
        self._report_event(EventType.MOTION_DETECTED if value else EventType.MOTION_STILL)


    def take_photo(self):
        tmp_file = NamedTemporaryFile(delete=False)
        self.camera.capture(tmp_file, format='jpeg', use_video_port=True, quality=60)
        tmp_file.flush()
        tmp_file.close()
        self._report_event(EventType.PHOTO_READY, tmp_file.name)

    def take_video(self):
        self.manual_rec = True

    def _report_event(self, event_type, file_name = None):
        pass

    def spin(self):
        if self._recorder.age_of_last_keyframe > self._recorder.age_limit:
            # Request a keyframe to allow hotswapping
            self.camera.request_key_frame()
        if self.manual_rec and self._recorder.oldest.age_in_frames > 30 * 8:
            # Manual recording has expired
            self.manual_rec = False


class CameraProcess(CameraManager):
    def __init__(self, state):
        super(CameraProcess, self).__init__()
        self.state = state

    def __enter__(self):
        super(CameraProcess, self).__enter__()
        log().info('CameraProcess: enter.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        log().info('CameraProcess: exit.')
        super(CameraProcess, self).__exit__(exc_type, exc_val, exc_tb)

    def _report_event(self, event_type, file_name = None):
        if event_type == EventType.VIDEO_READY:
            self.state.push_media(file_name, 'video')
            log().info('CameraProcess: video ready at %s' % file_name)
        elif event_type == EventType.PHOTO_READY:
            self.state.push_media(file_name, 'photo')
            log().info('CameraProcess: photo ready at %s' % file_name)
        elif event_type == EventType.MOTION_DETECTED:
            log().info('CameraProcess: motion detected.')
            self.state.motion_began = True
        elif event_type == EventType.MOTION_STILL:
            log().info('CameraProcess: motion still.')
            self.state.motion_stopped = True

    def spin(self):
        super(CameraProcess, self).spin()
        if self.state.photo_request:
            self.take_photo()
        if self.state.video_request:
            self.take_video()
