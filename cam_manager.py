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

class CameraMode(Enum):
    PHOTO = {'sensor_mode': 3, 'shutter_speed': 200000, 'resolution': '1640x1232'}
    VIDEO = {'sensor_mode': 4, 'framerate': 15, 'resolution': '640x480'}
    DEFAULT = {'iso': 800, 'sensor_mode': 3, 'exposure_mode': 'night'}

class CameraManager:
    def __getattr__(self, key):
        if key == 'mode':
            return self._mode
        elif key == 'cam':
            return self._cam
        else:
            return super(CameraManager, self).__getattr__(key)

    def __setattr__(self, key, value):
        if key == 'mode':
            self._set_mode(value)
        else:
            super(CameraManager, self).__setattr__(key, value)

    def _set_mode(self, mode):
        if mode != self._mode:
            for k, v in mode.value.items():
                if getattr(self._cam, k, None) != v:
                    setattr(self._cam, k, v)

    def __init__(self):
        self._cam = PiCamera()
        self._mode = None
        # Initialize default settings
        self.mode = CameraMode.DEFAULT
