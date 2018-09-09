import logging
import os

try:
    from picamera.array import PiMotionAnalysis
    from picamera.frames import PiVideoFrameType, PiVideoFrame

    assert PiVideoFrameType.frame == 0, 'Please update the except clause to reflect the changes in Picamera!'
    assert PiVideoFrameType.key_frame == 1, 'Please update the except clause to reflect the changes in Picamera!'
    assert PiVideoFrameType.sps_header == 2, 'Please update the except clause to reflect the changes in Picamera!'
    assert PiVideoFrameType.motion_data == 3, 'Please update the except clause to reflect the changes in Picamera!'

    # If the assertion right above triggers, please copy PiVideoFrameType in the except clause wuch that the unit tests
    # can still be run
except (ImportError, OSError):
    from collections import namedtuple

    class PiMotionAnalysis:
        def __init__(self, camera, *_, __=None):
            self.camera = camera

    class PiVideoFrameType:
        frame = 0
        key_frame = 1
        sps_header = 2
        motion_data = 3

    PiVideoFrame = namedtuple('PiVideoFrame', ['index', 'frame_type', 'frame_size', 'video_size', 'split_size',
                                               'timestamp', 'complete'])

_location_of_picamera_mp4 = None
try:
    from picamera.mp4 import MP4Muxer
except OSError as os_import_error:
    logging.warning('You have a Picamera install, but it seems it has failed to import.')
    logging.warning('I am assuming you patched Picamera for local install, e.g. for testing.')
    logging.warning('I will import MP4Muxer form Picamera bypassing picamera/__init__.py.')
    logging.debug('This hack is ugly as.')
    import importlib.util
    picamera_mod = importlib.util.find_spec('picamera')
    if picamera_mod is None:
        logging.error('Cannot find picamera via importlib. Will raise the import error.')
        raise os_import_error
    for location in picamera_mod.submodule_search_locations:
        if os.path.isfile(os.path.join(location, 'mp4.py')):
            _location_of_picamera_mp4 = location
            break
    if _location_of_picamera_mp4 is None:
        logging.error('Cannot find picamera.mp4 via importlib and manual lookup. Is MP4Muxer still in mp4.py?'
                      ' Will raise the import error.')
        raise os_import_error
    logging.warning('Found submodule search path as %s', _location_of_picamera_mp4)
    import sys
    sys.path.insert(0, _location_of_picamera_mp4)
    from mp4 import MP4Muxer
    logging.warning('I managed to import MP4Muxer with a broken Picamera install :)')
except Exception as e:
    logging.error('I did not manage to import MP4Muxer, error: %s', str(e))

    class MP4Muxer:
        def begin(self):
            raise NotImplementedError('This is a mockup.')

        def end(self, *_):
            raise NotImplementedError('This is a mockup.')

        def append(self, *_):
            raise NotImplementedError('This is a mockup.')
finally:
    if _location_of_picamera_mp4 is not None:
        sys.path.remove(_location_of_picamera_mp4)
