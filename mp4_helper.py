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

from muxer import OnlineMP4Muxer
from picamera import PiVideoFrameType

class PiMP4Output(object):

    def __init__(self, stream, camera):
        super(PiMP4Output, self).__init__()
        self.muxer = OnlineMP4Muxer(stream, camera.framerate, camera.resolution)
        self.camera = camera
        self.muxer.__enter__()

    def write(self, buf):
        self.muxer.append(buf, (self.camera.frame.frame_type == PiVideoFrameType.sps_header), self.camera.frame.complete)

    def flush(self):
        self.muxer.__exit__()

