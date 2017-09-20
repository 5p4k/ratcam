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
import logging

_log = logging.getLogger('ratcam')


CAM_BITRATE = 1500000
CAM_RESOLUTION = '720p'
CAM_FRAMERATE = 30
CAM_JPEG_QUALITY = 10
CAM_VIDEO_DURATION = 8
CAM_MOTION_WINDOW = 2


class CookedMotionDetector(DecayMotionDetector, PiMotionAnalysis):
    def __init__(self, camera_mgr):
        DecayMotionDetector.__init__(self, camera_mgr.camera.resolution, int(camera_mgr.camera.framerate))
        PiMotionAnalysis.__init__(self, camera_mgr.camera)
        self.camera_mgr = camera_mgr

    def analyze(self, a):
        self.process_motion_vector(a)

    def _trigger_changed(self):
        self.camera_mgr.motion_rec = self.is_triggered


class CookedDelayedMP4Recorder(DelayedMP4Recorder):
    def __init__(self, camera_mgr):
        super(CookedDelayedMP4Recorder, self).__init__(camera_mgr.camera, CAM_MOTION_WINDOW * int(camera_mgr.camera.framerate))
        self.camera_mgr = camera_mgr

    def _mp4_ready(self, file_name):
        self.camera_mgr.state.push_media(tmp_file.name, 'video')


class CameraManager:
    def __init__(self, state):
        self._camera = PiCamera()
        # Initialize default settings
        self._setup_camera()
        self._detector = CookedMotionDetector(self)
        self._recorder = CookedDelayedMP4Recorder(self)
        self._manual_rec = False
        self._motion_rec = False
        self._detection_enabled = False
        self.state = state

    def __enter__(self):
        self._camera.start_recording(self._recorder,
            format='h264', motion_output=self._detector, quality=None, bitrate=CAM_BITRATE)
        _log.info('CameraProcess: enter.')


    def __exit__(self, exc_type, exc_val, exc_tb):
        _log.info('CameraProcess: exit.')
        self.camera.stop_recording()

    def _setup_camera(self):
        # self.camera.iso = 800
        # self.camera.sensor_mode = 3
        # self.camera.exposure_mode = 'night'
        self.camera.resolution = CAM_RESOLUTION
        self.camera.framerate = CAM_FRAMERATE

    def _set_keep_recording(self):
        self._recorder.keep_recording = self._motion_rec or self._manual_rec

    @property
    def detection_enabled(self):
        return self._detection_enabled

    @property
    def camera(self):
        return self._camera

    @property
    def manual_rec(self):
        return self._manual_rec

    @property
    def motion_rec(self):
        return self._motion_rec

    @detection_enabled.setter
    def detection_enabled(self, value):
        if value != self._detection_enabled:
            self._detection_enabled = value
            if not value:
                self._motion_rec = False
                self._set_keep_recording()

    @manual_rec.setter
    def manual_rec(self, value):
        self._manual_rec = value
        self._set_keep_recording()

    @moving.setter
    def motion_rec(self, value):
        if self.detection_enabled:
            self._motion_rec = value
            self._set_keep_recording()
            self.state.motion_detected = value


    def take_photo(self):
        tmp_file = NamedTemporaryFile(delete=False)
        self.camera.capture(tmp_file, format='jpeg', use_video_port=True, quality=CAM_JPEG_QUALITY)
        tmp_file.flush()
        tmp_file.close()
        self.state.push_media(tmp_file.name, 'photo')
        self._report_event(EventType.PHOTO_READY, tmp_file.name)

    def _report_event(self, event_type, file_name = None): # FIX: why two classes
        pass

    def spin(self):
        if self._recorder.age_of_last_keyframe > int(self.camera.framerate):
            # Request a keyframe to allow hotswapping
            self.camera.request_key_frame()
        if self.state.video.get_and_clear_request():
            self.manual_rec = True
        if self.state.photo.get_and_clear_request():
            self.take_photo()
        if self.manual_rec and self._recorder.oldest.age_in_frames > int(self.camera.framerate) * CAM_VIDEO_DURATION:
            # Manual recording has expired
            self.manual_rec = False

