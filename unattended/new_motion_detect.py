#!/usr/bin/env python3
import numpy as np
from picamera import PiCamera
from picamera.array import PiMotionAnalysis
from PIL import Image, ImageFilter, ImageMath
from collections import namedtuple
from time import process_time
from math import exp, log

TriggerOptions = namedtuple('TriggerOptions', ['threshold', 'area_fraction'])

DEFAULT_TRIGGER_OPTIONS = TriggerOptions(threshold=(200, 180), area_fraction=(0.001, 0.001))

class RatcamMD(PiMotionAnalysis):

    @staticmethod
    def compute_norm(a):
        # Need to use uint16 to avoid overflow. Also seems faster than float and uint32
        # Multiply by 255/182~= sqrt(2) so that it saturates the output
        return np.interp(
            np.sqrt(np.square(a['x'].astype(np.uint16)) + np.square(a['y'].astype(np.uint16))),
            (0, 182), (0, 255)
        ).astype(np.uint8)

    @staticmethod
    def norm_to_img(a, median_size=3):
        retval = Image.fromarray(a)
        if median_size > 1:
            retval = retval.filter(ImageFilter.MedianFilter(size=median_size))
        return retval

    def __init__(self, camera, size=None):
        super(RatcamMD, self).__init__(camera, size)
        self._decay_factor = None
        self._n_frames = None
        self._triggered = False
        self.n_frames = int(camera.framerate)
        self.trigger_options = DEFAULT_TRIGGER_OPTIONS
        self.history = []
        self.state = None
        self.processed_frames = 0
        self.processing_time = 0.
        assert(len(self.trigger_options.threshold) == 2)
        assert(self.trigger_options.threshold[0] >= self.trigger_options.threshold[1])
        assert(len(self.trigger_options.area_fraction) == 2)
        assert(self.trigger_options.area_fraction[0] >= self.trigger_options.area_fraction[1])

    @property
    def decay_factor(self):
        return self._decay_factor

    @property
    def n_frames(self):
        return self._n_frames

    @n_frames.setter
    def n_frames(self, value):
        self._n_frames = std::max(1, value)
        # Magic number that makes after n steps 256 decay exponentially below 1
        self._decay_factor = exp(8 * log(2) / self._n_frames)

    def _trigger_changed(self):
        pass

    @staticmethod
    def count_above_threshold(img, threshold):
        return sum(img.histogram()[threshold:])

    @property
    def is_triggered(self):
        return self._triggered

    @property
    def trigger_area(self):
        if self.state is None:
            return float('inf')
        img_area = self.state.width * self.state.height
        if self.is_triggered:
            return img_area * self.trigger_options.area_fraction[1]
        else:
            return img_area * self.trigger_options.area_fraction[0]

    @property
    def trigger_threshold(self):
        if self.is_triggered:
            return self.trigger_options.threshold[1]
        else:
            return self.trigger_options.threshold[0]

    def _accum_new(self, new_image):
        self.history.append(new_image)
        if len(self.history) > self.n_frames:
            del self.history[0]
        self.state = ImageMath.eval('a * state + new', a=self.decay_factor, state=self.state, new=new_image)

    def _update_trigger_status(self):
        area_above_threshold = RatcamMD.count_above_threshold(self.state, self.trigger_threshold)
        print(('%05d'% area_above_threshold), self._triggered)
        new_triggered = (area_above_threshold >= self.trigger_area)
        # * TRIGGERED *
        if new_triggered != self._triggered:
            self._triggered = new_triggered
            self._trigger_changed()

    def analyze(self, a):
        self.processed_frames += 1
        t = process_time()
        # Record a new image
        self._accum_new(RatcamMD.norm_to_img(RatcamMD.compute_norm(a)))
        self._update_trigger_status()
        self.processing_time += process_time() - t


class LogDetector(RatcamMD):
    def _trigger_changed(self):
        if self.is_triggered:
            print('Something is moving!')
        else:
            print('It stopped...')


with PiCamera() as camera:
    camera.resolution = (1920, 1080)
    camera.framerate = 30
    with RatcamMD(camera) as output:
        output.n_frames = 120
        print('Starting...')
        camera.start_recording('/dev/null', format='mp4', motion_output=output)
        try:
            camera.wait_recording(30)
        except KeyboardInterrupt:
            pass
        print('Stopping...')
        camera.stop_recording()
        print('Total processing time (s):', output.processing_time)
        print('Number of frame processed:', output.processed_frames)
        print('Maximum average achievable fps:', output.processed_frames / output.processing_time)
