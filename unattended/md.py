#!/usr/bin/env python3
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
from picamera.array import PiMotionAnalysis
from detector import RatcamMD

class LogDetector(RatcamMD, PiMotionAnalysis):
    def __init__(self, camera, size=None):
        RatcamMD.__init__(self, camera.resolution, int(camera.framerate))
        PiMotionAnalysis.__init__(self, camera, size)

    def _trigger_changed(self):
        if self.is_triggered:
            print('Something is moving!')
        else:
            print('It stopped...')

    def analyze(self, a):
        self.process_motion_vector(a)


with PiCamera() as camera:
    camera.resolution = (1920, 1080)
    camera.framerate = 30
    with LogDetector(camera) as output:
        output.n_frames = 120
        print('Starting...')
        camera.start_recording('/dev/null', format='mp4', motion_output=output)
        try:
            camera.wait_recording(30)
        except KeyboardInterrupt:
            pass
        print('Stopping...')
        camera.stop_recording()
        print('Total processing time (s):', output.processing_time)
        print('Number of frame processed:', output.processed_frames)
        print('Maximum average achievable fps:', output.processed_frames / output.processing_time)
