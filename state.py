from multiprocessing import Event
import os
import queue

import logging

_log = logging.getLogger()

class SharedState:
    def __init__(self, manager):
        self._video_request = manager.Event()
        self._photo_request = manager.Event()
        self._motion_began = manager.Event()
        self._motion_stopped = manager.Event()
        self._media_queue = manager.Queue(10)

    @property
    def video_request(self):
        if self._video_request.is_set():
            self._video_request.clear()
            return True
        return False

    @property
    def photo_request(self):
        if self._photo_request.is_set():
            self._photo_request.clear()
            return True
        return False

    @property
    def motion_began(self):
        if self._motion_began.is_set():
            self._motion_began.clear()
            return True
        return False

    @property
    def motion_stopped(self):
        if self._motion_stopped.is_set():
            self._motion_stopped.clear()
            return True
        return False

    @video_request.setter
    def video_request(self, value):
        if value:
            self._video_request.set()
        # else: do nothing

    @photo_request.setter
    def photo_request(self, value):
        if value:
            self._photo_request.set()
        # else: do nothing

    @motion_began.setter
    def motion_began(self, value):
        if value:
            self._motion_began.set()
        # else: do nothing

    @motion_stopped.setter
    def motion_stopped(self, value):
        if value:
            self._motion_stopped.set()
        # else: do nothing

    def push_media(self, file_name, type):
        try:
            self._media_queue.put((file_name, type), block=False)
        except queue.Full:
            _log.warning('Media queue is full, deleting %s %s.' % (type, file_name))
            os.remove(file_name)

    def pop_media(self):
        try:
            return self._media_queue.get(block=False)
        except queue.Empty:
            return (None, None)
