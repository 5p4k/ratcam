from tempfile import NamedTemporaryFile
import os
import logging
from safe_picamera import MP4Muxer


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


class TemporaryMP4Muxer:
    """
    A MP4 muxer that writes to a temporary file, that can be rewinded at need.
    """

    def __init__(self):
        self._temp_file = None
        self._muxer = None
        self._age = None
        self._last_frame_is_complete = False

    def __enter__(self):
        self._setup_new_temp()

    def _setup_new_temp(self):
        self._temp_file = NamedTemporaryFile(delete=False)
        self._muxer = MP4StreamMuxer(self._temp_file)
        self._muxer.begin()
        self._age = 0

    def _discard_temp(self):
        self._temp_file.close()
        self._muxer = None
        if os.path.isfile(self._temp_file.name):
            logging.debug('Dropping temporary MP4 %s', self._temp_file.name)
            try:
                os.remove(self._temp_file.name)
            except OSError as e:
                logging.error('Unable to remove {}, error: {}'.format(self._temp_file.name, e.strerror))
        self._temp_file = None
        self._muxer = None
        self._age = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._discard_temp()

    @property
    def age(self):
        return self._age

    @property
    def file_name(self):
        return self._temp_file.name

    def rewind(self):
        if not self._last_frame_is_complete:
            raise RuntimeError('Rewinding before the last frame is complete will corrupt the media.')
        self._temp_file.seek(0)
        # Need to create new because it will seek to the mdat offset for finalizing the mp4
        self._muxer = MP4StreamMuxer(self._temp_file)
        self._muxer.begin()
        self._age = 0

    def finalize(self, framerate, resolution):
        """
        Finalized the current MP4 and returns the file name.
        Continues recording on another temporary file
        """
        if not self._last_frame_is_complete:
            raise RuntimeError('Finalizing before the last frame is complete will corrupt the media.')
        old_temp_file, old_muxer = self._temp_file, self._muxer
        self._setup_new_temp()
        # Now we can work safely with the old muxer and temp files
        old_temp_file.flush()
        old_temp_file.truncate()
        old_muxer.end(framerate, resolution)
        old_temp_file.close()
        logging.debug('Finalized MP4 file %s' % old_temp_file.name)
        return old_temp_file.name

    def append(self, data, frame_is_sps_header, frame_is_complete):
        self._muxer.append(data, frame_is_sps_header, frame_is_complete)
        if frame_is_complete and not frame_is_sps_header:
            self._age += 1
        self._last_frame_is_complete = frame_is_complete


class DualBufferedMP4:
    def __init__(self):
        self._old = TemporaryMP4Muxer()
        self._new = TemporaryMP4Muxer()
        self._is_recording = False
        self._total_age = 0

    @property
    def buffer_age(self):
        return self._new.age if self.is_recording else self._old.age

    @property
    def footage_age(self):
        return self._old.age

    @property
    def total_age(self):
        return self._total_age

    @property
    def is_recording(self):
        return self._is_recording

    def record(self):
        self._is_recording = True

    def rewind_buffer(self):
        if self.is_recording:
            self._new.rewind()
        else:
            self._old.rewind()
            self._old, self._new = self._new, self._old

    def append(self, data, frame_is_sps_header, frame_is_complete):
        self._old.append(data, frame_is_sps_header, frame_is_complete)
        self._new.append(data, frame_is_sps_header, frame_is_complete)
        if not frame_is_sps_header and frame_is_complete:
            self._total_age += 1

    def stop_and_finalize(self, framerate, resolution):
        self._is_recording = False
        self._old, self._new = self._new, self._old
        return self._new.finalize(framerate, resolution)

    def stop_and_discard(self):
        self._is_recording = False
        self.rewind_buffer()

    def __enter__(self):
        self._old.__enter__()
        self._new.__enter__()
        self._is_recording = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._new.__exit__(exc_type, exc_val, exc_tb)
        self._old.__exit__(exc_type, exc_val, exc_tb)
