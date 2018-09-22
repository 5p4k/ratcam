from plugins.base import PluginProcessBase, Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin, active_plugins
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway
import logging
from misc.logging import ensure_logging_setup, camel_to_snake
from misc.settings import SETTINGS
from specialized.plugin_picamera import PiCameraProcessBase
from math import log, exp
from specialized.detector_support.imaging import get_denoised_motion_vector_norm
import numpy as np
from specialized.support.thread_host import CallbackThreadHost


MOTION_DETECTOR_PLUGIN_NAME = 'MotionDetector'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(MOTION_DETECTOR_PLUGIN_NAME))


class MotionDetectorResponder(PluginProcessBase):
    @classmethod
    def process(cls):  # pragma: no cover
        return Process.MAIN

    @property
    def motion_detector_plugin(self):
        return find_plugin(MOTION_DETECTOR_PLUGIN_NAME).camera

    def _motion_status_changed_internal(self, is_moving):
        pass

    @pyro_oneway
    @pyro_expose
    def motion_status_changed(self, is_moving):
        self._motion_status_changed_internal(is_moving)


@make_plugin(MOTION_DETECTOR_PLUGIN_NAME, Process.MAIN)
class PluginMotionDetectorMainComp(PiCameraProcessBase):
    def __init__(self):
        super(PluginMotionDetectorMainComp, self).__init__()
        self._notify_thread = CallbackThreadHost('notify_movement_thread', self._notify_movement)

    def __enter__(self):
        super(PluginMotionDetectorMainComp, self).__enter__()
        self._notify_thread.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._notify_thread.__exit__(exc_type, exc_val, exc_tb)
        super(PluginMotionDetectorMainComp, self).__exit__(exc_type, exc_val, exc_tb)

    def _notify_movement(self):
        value = find_plugin(self, Process.CAMERA).triggered
        for plugin_name, plugin in active_plugins().items():
            if plugin.main is None or not isinstance(plugin.main, MotionDetectorResponder):
                continue
            try:
                plugin.motion_status_changed(value)
            except Exception as exc:  # pragma: no cover
                _log.error('Plugin %s has triggered an exception during motion_status_changed: %s',
                           plugin_name, str(exc))

    @pyro_oneway
    @pyro_expose
    def notify_movement_status_changed(self):
        self._notify_thread.wake()


@make_plugin(MOTION_DETECTOR_PLUGIN_NAME, Process.CAMERA)
class PluginMotionDetectorCameraComp(PiCameraProcessBase):
    def __init__(self):
        super(PluginMotionDetectorCameraComp, self).__init__()
        self._trigger_thresholds = None
        self._trigger_area_fractions = None
        self._time_window = None
        self._accumulator = None
        self._triggered = False
        # Load settings' defaults
        self.trigger_thresholds = SETTINGS.detector.trigger_thresholds
        self.trigger_area_fractions = SETTINGS.detector.trigger_area_fractions
        self.time_window = SETTINGS.detector.time_window

    @pyro_expose
    @property
    def trigger_thresholds(self):
        return self._trigger_thresholds

    @pyro_expose
    @property
    def trigger_area_fractions(self):
        return self._trigger_area_fractions

    @pyro_expose
    @property
    def time_window(self):
        return self._time_window

    @pyro_expose
    @property
    def triggered(self):
        return self._triggered

    @pyro_expose
    @property
    def motion_estimate(self):
        return self._accumulator

    @pyro_expose
    @trigger_thresholds.setter
    def trigger_thresholds(self, value):
        self._trigger_thresholds = tuple(map(lambda x: min(max(int(x), 0), 255), value))[:2]
        assert len(self.trigger_thresholds) == 2

    @pyro_expose
    @trigger_area_fractions.setter
    def trigger_area_fractions(self, value):
        self._trigger_area_fractions = tuple(map(lambda x: min(max(float(x), 0.0), 1.0), value))[:2]
        assert len(self.trigger_thresholds) == 2

    @pyro_expose
    @time_window.setter
    def time_window(self, time):
        self._time_window = min(max(float(time), 0.01), 10000.)

    @property
    def _decay_factor(self):
        # Magic number that makes after n steps 256 decay exponentially below 1
        return exp(-8 * log(2) / (self.time_window * self.picamera_root_plugin.camera.framerate))

    @property
    def _frame_area(self):
        w, h = self.picamera_root_plugin.camera.resolution
        return w * h

    def _updated_trigger_status(self):
        threshold = self.trigger_thresholds[1 if self.triggered else 0]
        min_area = self.trigger_area_fractions[1 if self.triggered else 0] * self._frame_area
        movement_amount_above_thresholds = (np.sum(self._accumulator > threshold) >= min_area)
        if movement_amount_above_thresholds != self.triggered:
            self._triggered = movement_amount_above_thresholds
            find_plugin(self, Process.MAIN).notify_movement_status_changed()

    def analyze(self, array):  # pragma: no cover
        array = get_denoised_motion_vector_norm(array)
        if self._accumulator is None:
            self._accumulator = array
        else:
            self._accumulator *= self._decay_factor
            self._accumulator += array
        self._updated_trigger_status()
