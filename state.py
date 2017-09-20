from multiprocessing import Event, Value
import os
import queue
from collections import namedtuple

import logging

_log = logging.getLogger('ratcam')


class Switch:
    def __init__(self, manager):
        self._value = manager.Value('B', 0)
        self._changed = manager.Event()

    @property
    def value(self):
        return self._value.value != 0

    @value.setter
    def value(self, new_val):
        with self._value.get_lock():
            if new_val != self.value:
                self._value.value = 1 if new_val else 0
                if self._changed.is_set():
                    self._changed.clear()
                else:
                    self._changed.set()

    def get_last_change(self):
        with self._value.get_lock():
            if self._changed.is_set():
                self._changed.clear()
                return self.value
            return None

class Request:
    def __init__(self, manager):
        self._event = manager.Event()

    def request(self):
        self._event.set()

    def get_and_clear_request(self):
        if self._event.is_set():
            self._event.clear()
            return True
        return False


class SharedState:
    def __init__(self, manager):
        self._motion_detected = Switch(manager)
        self._detection_enabled = Switch(manager)
        self.video = Request(manager)
        self.photo = Request(manager)
        self._media_queue = manager.Queue(10)


    @property
    def motion_detected(self):
        return self._motion_detected.value

    @motion_detected.setter
    def motion_detected(self, value):
        self._motion_detected.value = value

    @property
    def motion_detected_change(self):
        return self._motion_detected.get_last_change()

    @property
    def detection_enabled(self):
        return self._detection_enabled.value

    @detection_enabled.setter
    def detection_enabled(self, value):
        self._detection_enabled.value = value

    @property
    def detection_enabled_change(self):
        return self._detection_enabled.get_last_change()

    @property
    def detection_switch(self):
        return self._detection_switch.is_set()

    @detection_switch.setter
    def detection_switch(self, value):
        if value:
            self._detection_switch.set()
        else:
            self._detection_switch.clear()

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
