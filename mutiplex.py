from tempfile import NamedTemporaryFile
from picamera.mp4 import MP4Muxer
from picamera.frames import PiVideoFrameType
import os
import os.path

class PiFrameDataOutput:
    """
    Transfers also frame information to another output
    """
    def __init__(self, camera, target):
        self.camera = camera
        self.target = target

    def write(self, data):
        self.target.write(data, self.camera.frame)

    def flush(self):
        self.target.flush()


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
        # Complete the MP4 and close the file
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
    def foo(self):
        if next_frame_is_key:
            if self.oldest.age_in_frames > self.age_limit and not self.keep_recording:
                self.oldest.reset()
                # blabla