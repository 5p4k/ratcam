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
from PIL import Image
import numpy as np
from legacy.detector import DecayMotionDetector
from glob import glob
from time import process_time

class DummyDetector(DecayMotionDetector):
    def __init__(self, size, *args, **kwargs):
        super(DummyDetector, self).__init__(size, *args, **kwargs)
        self.size = size

    def _trigger_changed(self):
        if self.is_triggered:
            print('Frame %s: something is moving!' % self.path)
        else:
            print('Frame %s: it stopped...' % self.path)

    def process_motion_vector(self, a):
        # Patch process_motion_vector not to extract the norm but to take the array as it is
        self.processed_frames += 1
        t = process_time()
        # Record a new image
        self._accum_new(a)
        self._update_trigger_status()
        self.processing_time += process_time() - t


    def analyze(self, path):
        self.path = path
        data = np.array(Image.open(path).getdata()).astype(np.float)
        self.process_motion_vector(data)
        Image.fromarray(self.motion_accumulator.clip(0, 255).astype(np.uint8).reshape(self.size[1], self.size[0])).save('accum%03d.png' % self.processed_frames)


def main():
    pngs = sorted(glob('*.png'))
    # Extract resolution
    first_png = Image.open(pngs[0])
    d = DummyDetector(first_png.size, 60)
    for png in pngs:
        d.analyze(png)
    print('Completed.')

if __name__ == '__main__':
    main()