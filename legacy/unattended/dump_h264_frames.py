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
import numpy as np
import picamera
import picamera.array
from PIL import Image

class MyOutput(object):
    def __init__(self, cam):
        self.stream = None
        self.cam = cam
        self.size = 0
        self.frames = []

    def __enter__(self):
        self.stream = open('vout.h264', 'wb')
        return self

    def write(self, s):
        self.stream.write(s)
        self.size += len(s)
        if self.cam.frame.complete:
            self.frames.append(self.cam.frame)

    def flush(self):
        self.stream.flush()

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream.close()

if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (1920, 1080)
        camera.framerate = 30
        print('Warming up camera...')
        sleep(2)
        print('Recording...')
        with MyOutput(camera) as output:
            with picamera.array.PiMotionArray(camera) as motion_stream:
                camera.start_recording(output, format='h264', motion_output=motion_stream)
                camera.wait_recording(2)
                camera.request_key_frame()
                camera.wait_recording(4)
                camera.stop_recording()
                print('Flushed %d bytes' % output.size)
                print('List of captured frames:')
                for f in output.frames:
                    print('  %s' % repr(f))
                print('Total: %d frames at %s fps.' % (len(output.frames), str(camera.framerate)))
                for frame in range(motion_stream.array.shape[0]):
                    data = np.sqrt(
                        np.square(motion_stream.array[frame]['x'].astype(np.float)) +
                        np.square(motion_stream.array[frame]['y'].astype(np.float))
                        ).clip(0, 255).astype(np.uint8)
                    img = Image.fromarray(data)
                    filename = 'frame%03d.png' % frame
                    print('Writing %s' % filename)
                    img.save(filename)
