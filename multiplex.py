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
from picamera.frames import PiVideoFrameType, PiVideoFrame
import os
import os.path
import logging
from threading import Lock
from datetime import datetime

_log = logging.getLogger('ratcam')


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
        self.muxer = None
        self.age_in_frames = -1
        self.reset()

    def destroy(self):
        self.file.close()
        self.muxer = None
        if os.path.isfile(self.file.name):
            _log.debug('Dropping temporary MP4 %s' % self.file.name)
            os.remove(self.file.name)
        self.file = None
        self.age_in_frames = -1

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
        self.file.flush()
        self.file.truncate()
        self.muxer.end(framerate, resolution)
        self.file.close()
        # Put in place another file
        self.file = NamedTemporaryFile(delete=False)
        self.reset()
        return file_name

    def append(self, data, frame_is_sps_header, frame_is_complete):
        self.muxer.append(data, frame_is_sps_header, frame_is_complete)
        if frame_is_complete and not frame_is_sps_header:
            self.age_in_frames += 1


class DelayedMP4Recorder:
    def __init__(self, camera, age_limit):
        self.last_frame = PiVideoFrame(index=0, frame_type=None, frame_size=0, video_size=0,
                                       split_size=0, timestamp=0, complete=True)
        self._streams = [TempMP4Muxer()]
        self._keep_recording = False
        self._stopping_recording = False
        self._camera = camera
        self.age_limit = age_limit
        self.age_of_last_keyframe = 0
        self._stream_lock = Lock()
        self._last_date = datetime.now()

    def _mp4_ready(self, file_name):
        pass

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
        assert (len(self._streams) == 1)
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
        return self._keep_recording and not self._stopping_recording

    @keep_recording.setter
    def keep_recording(self, value):
        with self._stream_lock:
            if value == self._keep_recording:
                return
            if not self._keep_recording:
                _log.debug('Turning on persistent recording.')
                self._keep_recording = value
                # Can destroy the second stream
                self._drop_youngest()
            else:
                if self.last_frame.complete:
                    self._stop_recording()
                else:
                    # Postpone until the frame is completed
                    self._stopping_recording = True

    def _stop_recording(self):
        _log.debug('Turning off persistent recording, finalizing mp4 at path %s' % self.oldest.file.name)
        self._stopping_recording = False
        self._keep_recording = False
        # Can finalize the oldest stream
        self._mp4_ready(self.oldest.finalize(self._camera.framerate, self._camera.resolution))

    def write(self, data):
        # Update time as well
        if (datetime.now() - self._last_date).total_seconds() >= 1.:
            self._last_date = datetime.now()
            self._camera.annotate_text = self._last_date.strftime('%Y-%m-%d %H:%M:%S')
        is_sps_header = (self._camera.frame.frame_type == PiVideoFrameType.sps_header)
        is_complete = self._camera.frame.complete
        with self._stream_lock:
            if not self.keep_recording and self.last_frame.complete and is_sps_header:
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
            if self.last_frame.complete:
                if is_sps_header:
                    self.age_of_last_keyframe = 0
                else:
                    self.age_of_last_keyframe += 1
            if self._stopping_recording and is_complete:
                self._stop_recording()

    def flush(self):
        self.oldest.destroy()
        if self.youngest:
            self.youngest.destroy()
