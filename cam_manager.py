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

import numpy as np
from picamera.array import PiMotionAnalysis
from detector import DecayMotionDetector
from multiplex import DelayedMP4Recorder
from tempfile import NamedTemporaryFile
from picamera import PiCamera
from threading import Event
from colorize_motion import overlay_motionv
import logging

_log = logging.getLogger('ratcam')

CAM_BITRATE = 750000
CAM_RESOLUTION = '720p'
CAM_FRAMERATE = 30
CAM_JPEG_QUALITY = 7
CAM_VIDEO_DURATION = 8
CAM_MOTION_WINDOW = 2


def _sat_fn(x):
    return 4 * x if x < 50 else max(200, x)


def _hue_fn(x):
    if x < 50:
        return 138
    elif x > 200:
        return 204
    return int(138 + (x - 50) * 66 / 150)


SAT_LUT = [_sat_fn(x) for x in range(256)]
HUE_LUT = [_hue_fn(x) for x in range(256)]


class CookedMotionDetector(DecayMotionDetector, PiMotionAnalysis):
    def __init__(self, cam_mgr):
        DecayMotionDetector.__init__(self, cam_mgr.camera.resolution, int(cam_mgr.camera.framerate))
        PiMotionAnalysis.__init__(self, cam_mgr.camera)
        self.cam_mgr = cam_mgr

    def analyze(self, a):
        self.process_motion_vector(a)

    def _trigger_changed(self):
        self.cam_mgr._report_motion(self.is_triggered)


class CookedDelayedMP4Recorder(DelayedMP4Recorder):
    def __init__(self, cam_mgr):
        super(CookedDelayedMP4Recorder, self).__init__(
            cam_mgr.camera, CAM_MOTION_WINDOW * int(cam_mgr.camera.framerate))
        self.cam_mgr = cam_mgr

    def _mp4_ready(self, file_name):
        self.cam_mgr._report_mp4_ready(file_name)


class CameraManager:
    def __init__(self, bot_interface):
        self._camera = PiCamera()
        self._moving = False
        self._manual_rec = False
        self._detection_enabled = False
        self._bot_interface = bot_interface
        self._detector = CookedMotionDetector(self)
        self._recorder = CookedDelayedMP4Recorder(self)
        self._rgb_capture_array = None
        self._take_motion_image_evt = Event()
        self._setup_camera()

    def __enter__(self):
        self.camera.start_recording(
            self._recorder, format='h264', motion_output=self._detector,
            quality=None, bitrate=CAM_BITRATE)
        _log.info('Cam: enter.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        _log.info('Cam: exit.')
        self.camera.stop_recording()

    def _setup_camera(self):
        # self.camera.iso = 800
        # self.camera.sensor_mode = 3
        # self.camera.exposure_mode = 'night'
        self.camera.resolution = CAM_RESOLUTION
        self.camera.framerate = CAM_FRAMERATE
        self._rgb_capture_array = np.empty((self.camera.resolution[1], self.camera.resolution[0], 3), dtype=np.uint8)

    @property
    def camera(self):
        return self._camera

    @property
    def detection_enabled(self):
        return self._detection_enabled

    @detection_enabled.setter
    def detection_enabled(self, value):
        if value != self._detection_enabled:
            _log.info('Cam: detection is now %s', 'ON' if value else 'OFF')
            self._detection_enabled = value
            self._toggle_recording()

    def _report_motion(self, value):
        if self.detection_enabled:
            _log.info('Cam: motion detected.' if value else 'Cam: motion still.')
            self._bot_interface.push_motion_event(value)
            self._moving = value
            self._toggle_recording()
            if value:
                self._take_motion_image_evt.set()

    def _report_mp4_ready(self, file_name):
        _log.debug('Cam: video ready at %s', file_name)
        self._bot_interface.push_media(file_name, 'mp4')

    def _take_motion_image(self):
        # Get a rgb image of a size matching the motion vector
        self.camera.capture(self._rgb_capture_array, format='rgb', use_video_port=True)
        # Blend it to the motion vector using another routine
        img = overlay_motionv(self._rgb_capture_array, self._detector.motion_accumulator)
        # Make a temporary file where to save the data
        tmp_file = NamedTemporaryFile(delete=False)
        # Merge the bands, convert to RGB and save
        img.save(tmp_file, format='jpeg')
        tmp_file.flush()
        tmp_file.close()
        _log.debug('Cam: motion image ready at %s', tmp_file.name)
        return tmp_file.name

    def take_video(self):
        _log.info('Cam: manual recording is ON.')
        self._manual_rec = True
        self._toggle_recording()

    def take_photo(self):
        _log.info('Cam: taking photo.')
        tmp_file = NamedTemporaryFile(delete=False)
        self.camera.capture(tmp_file, format='jpeg', use_video_port=True, quality=CAM_JPEG_QUALITY)
        tmp_file.flush()
        tmp_file.close()
        _log.debug('Cam: photo ready at %s', tmp_file.name)
        self._bot_interface.push_media(tmp_file.name, 'jpeg')

    def spin(self):
        """
        Run this at least once a second
        """
        keyframe_age_limit = int(self.camera.framerate)
        video_age_limit = int(self.camera.framerate) * CAM_VIDEO_DURATION
        if self._recorder.age_of_last_keyframe > keyframe_age_limit:
            _log.debug('Last keframe age is %d, limit is %d. Requesting keyframe.', self._recorder.age_of_last_keyframe,
                       keyframe_age_limit)
            # Request a keyframe to allow hotswapping
            self.camera.request_key_frame()
        if self._manual_rec:
            if self._recorder.oldest.age_in_frames > video_age_limit:
                _log.debug('Recording video is %d frames old (limit: %d). Turning off manual rec.' %(
                    self._recorder.oldest.age_in_frames, video_age_limit
                ))
                # Manual recording has expired
                self._manual_rec = False
                self._toggle_recording()
        if self._take_motion_image_evt.is_set():
            self._take_motion_image_evt.clear()
            # Take and deliver a motion image
            self._bot_interface.push_media(self._take_motion_image(), 'jpeg')

    def _toggle_recording(self):
        keep_recording = self._manual_rec or (self.detection_enabled and self._moving)
        if keep_recording != self._recorder.keep_recording:
            _log.debug('Changing keep recording; manual rec: {}, detection enabled: {}, moving: {}'.format(
                self._manual_rec, self.detection_enabled, self._moving))
            self._recorder.keep_recording = keep_recording
