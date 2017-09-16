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

from tempfile import NamedTemporaryFile
from picamera.mp4 import MP4Muxer
from picamera.frames import PiVideoFrameType
import os
import os.path
from misc import log

class MP4StreamMuxer(MP4Muxer):
    """
    Simple MP4 muxer wrapper that writes and seeks on a stream.
    """
    def __init__(self, stream):
        super(MP4StreamMuxer, self).__init__()
        self.stream = stream

    def _write(self, data):
        self.stream.write(data)

    def _seek(self, offset):
        self.stream.seek(offset)

class TempMP4Muxer:
    """
    A MP4 muxer that writes to a temporary file, that can be reset to zero if needed.
    """
    def __init__(self):
        self.file = NamedTemporaryFile(delete=False)
        self.age_in_frames = 0

    def destroy(self):
        self.file.close()
        self.muxer = None
        if os.path.isfile(self.file.name):
            log().info('Removing temporary file %s' % self.file.name)
            os.remove(self.file.name)
        self.file = None
        self.age_in_frames = None

    def reset(self):
        self.file.seek(0)
        self.muxer = MP4StreamMuxer(self.file)
        self.muxer.begin()
        self.age_in_frames = 0

    def finalize(self, framerate, resolution):
        """
        Finalized the current MP4 and returns the file name.
        Continues recording on another temporary file
        """
        file_name = self.file.name
        # Output the MP4 footer and close the file
        self.muxer.end(framerate, resolution) # TODO truncate!
        self.file.close()
        # Put in place another file
        self.file  NamedTemporaryFile(delete=False)
        self.reset()
        return file_name

    def append(self, data, frame_is_sps_header, frame_is_complete):
        self.muxer.append(data, frame_is_sps_header, frame_is_complete)
        if frame_is_complete:
            self.age_in_frames += 1

class DelayedMP4Recorder:
    def __init__(self, camera, age_limit):
        self.frame = PiVideoFrame(index=0, frame_type=None, frame_size=0, video_size=0,
            split_size=0, timestamp=0, complete=True)
        self._streams = [TempMP4Muxer()]
        self._keep_recording = False
        self._camera = camera
        self.age_limit = age_limit
        self.recorded_files = []

    @property
    def oldest(self):
        if len(self._streams) == 1 or self._streams[0].age_in_frames >= self._streams[1].age_in_frames:
            return self._streams[0]
        else:
            return self._streams[1]

    @property
    def youngest(self):
        if len(self._streams) == 1:
            return None
        if self._streams[0].age_in_frames < self._streams[1].age_in_frames:
            return self._streams[0]
        else:
            return self._streams[1]

    def _init_second_stream(self):
        assert(len(self._streams) == 1)
        self._streams.append(TempMP4Muxer())

    def _drop_youngest(self):
        if self.youngest:
            self.youngest.destroy()
            if self._streams[0] == self.youngest:
                del self._streams[0]
            else:
                del self._streams[1]


    @property
    def keep_recording(self):
        return self._keep_recording

    @keep_recording.setter
    def keep_recording(self, value):
        if value == self._keep_recording:
            return
        self._keep_recording = value
        if self._keep_recording:
            log().info('Turning on persistend recording.')
            # Can destroy the second stream
            self._drop_youngest()
        else:
            log().info('Finalizing recording at path %s' % self.oldest.file.name)
            # Can finalize the oldest stream
            self.recorded_files.append(
                self.oldest.finalize(self._camera.framerate, self._camera.resolution))


    def write(self, data):
        is_sps_header = (self._camera.frame.frame_type == PiVideoFrameType.sps_header)
        is_complete = self._camera.frame.complete
        if self.keep_recording:
            # Just pass data down
            self.oldest.append(data, is_sps_header, is_complete)
        elif self.last_frame.complete and is_sps_header:
            # Can do syncing only at sps headers. Start the second stream up
            if self.oldest.age_in_frames > self.age_limit and not self.youngest:
                self._init_second_stream()
            elif self.oldest.age_in_frames > 2 * self.age_limit:
                # Time for a reset
                self.oldest.reset()
            # Write data to all streams
            self.oldest.append(data, is_sps_header, is_complete)
            if self.youngest:
                self.youngest.append(data, is_sps_header, is_complete)
        # Store the frame
        self.last_frame = self._camera.frame


    def flush(self):
        self.oldest.destroy()
        if self.youngest:
            self.youngest.destroy()