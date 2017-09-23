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

from collections import namedtuple
from datetime import datetime
import queue
import logging
import os

_log = logging.getLogger('ratcam')


CamCmd = namedtuple('CamCmd', ['video_request', 'photo_request', 'toggle_detection'])


B_TRUE = 1
B_FALSE = 0
B_NONE = 2


def b_to_bool(b):
    if b == B_TRUE:
        return True
    elif b == B_FALSE:
        return False
    elif b == B_NONE:
        return None
    else:
        assert(b in [B_TRUE, B_FALSE, B_NONE])


class CamInterface:
    """
    The camera can only poll a certain number of commands per unit of time.
    """
    def __init__(self, proc_mgr):
        self._video_request = proc_mgr.Value('b', B_FALSE)
        self._photo_request = proc_mgr.Value('b', B_FALSE)
        self._toggle_detection = proc_mgr.Value('b', B_NONE)
        self._changed_event = proc_mgr.Event()

    def _as_cmd(self):
        return CamCmd(video_request=b_to_bool(self._video_request.value),
                      photo_request=b_to_bool(self._photo_request.value),
                      toggle_detection=b_to_bool(self._toggle_detection.value))

    def _reset(self):
        self._changed_event.clear()
        self._video_request.value = B_FALSE
        self._photo_request.value = B_FALSE
        self._toggle_detection.value = B_NONE

    def pop_cmd_if_changed(self, timeout):
        if self._changed_event.wait(timeout=timeout):
            retval = self._as_cmd()
            self._reset()
            return retval
        return None

    def request_video(self):
        self._video_request.value = B_TRUE
        self._changed_event.set()

    def request_photo(self):
        self._photo_request.value = B_TRUE
        self._changed_event.set()

    def toggle_detection(self, value):
        self._toggle_detection.value = B_TRUE if value else B_FALSE
        self._changed_event.set()


class BotInterface:
    def __init__(self, proc_mgr):
        self._media_queue = proc_mgr.Queue()
        self._notifications_queue = proc_mgr.Queue()

    def pop_motion_event(self, timeout):
        try:
            return self._notifications_queue.get(True, timeout=timeout)
        except queue.Empty:
            pass
        except Exception as e:
            _log.warning('Cannot pop from motion events: %s' % str(e))
        return None, None

    def pop_media(self, timeout):
        try:
            return self._media_queue.get(True, timeout=timeout)
        except queue.Empty:
            pass
        except Exception as e:
            _log.warning('Cannot pop from media: %s' % str(e))
        return None, None

    def push_motion_event(self, motion_detected):
        try:
            self._notifications_queue.put((datetime.now(), motion_detected), False)
        except queue.Full:
            _log.error('Cannot push motion event: queue full.')
        except Exception as e:
            _log.error('Cannot push motion event: %s' % str(e))

    def push_media(self, media_file, media_type):
        try:
            self._media_queue.put((media_file, media_type), False)
            return
        except queue.Full:
            _log.error('Cannot push motion event: queue full.')
        except Exception as e:
            _log.error('Cannot push motion event: %s' % str(e))
        _log.warning('Removing media file %s' % media_file)
        os.remove(media_file)
