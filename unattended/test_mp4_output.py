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
from time import sleep
import picamera

if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (640, 480)
        camera.framerate = 15
        print('Warming up camera...')
        sleep(2)
        print('Recording...')
        camera.start_recording('video.mp4')
        camera.wait_recording(2)
        camera.stop_recording()

