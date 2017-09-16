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

from multiplex import DelayedMP4Recorder
import picamera

if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (640, 480)
        camera.framerate = 15
        recorder = DelayedMP4Recorder(camera, 15)
        camera.start_recording(recorder, format='h264')
        print('Beginning real recording in...')
        for i in range(5):
            print(5 - i)
            camera.request_key_frame()
            camera.wait_recording(1)
        print('Recording for real some 4 seconds.')
        recorder.keep_recording = True
        camera.wait_recording(4)
        recorder.keep_recording = False
        print('Running some keyframes...')
        for i in range(5):
            print(1 + i)
            camera.request_key_frame()
            camera.wait_recording(1)
        print('Done')
        camera.stop_recording()

