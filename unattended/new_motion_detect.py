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

def Pillow_median(a, size=3, reshape=False):
    filt = ImageFilter.MedianFilter(size=size)
    b = np.array(Image.fromarray(a).filter(filt).getdata())
    if reshape:
        b = b.reshape(a.shape)
    return b


class RatcamMD:

    @staticmethod
    def compute_and_denoise_mv_norm(a, median_size=3, reshape=False, dtype=np.uint16):
        # Need to use uint16 to avoid overflow. Also seems faster than float and uint32
        norm = np.sqrt(np.square(a['x'].astype(np.uint16)) + np.square(a['y'].astype(np.uint16)))
        # Scale to fill. Max norm value for 8bit signed vectors is ~182
        norm = np.interp(norm, (0, 182), (0, 255)).astype(np.uint8)
        # Apply median filter
        if median_size > 1:
            norm = Pillow_median(norm, size=median_size, reshape=reshape)
        # Convert to destination type
        return norm.astype(dtype)

    def __init__(self, resolution, n_frames):
        self._decay_factor = None
        self._n_frames = None
        self._triggered = False
        self._resolution_area = resolution[0] * resolution[1]
        self.n_frames = n_frames
        self.trigger_options = DEFAULT_TRIGGER_OPTIONS
        self.motion_accumulator = None
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
        self._decay_factor = exp(-8 * log(2) / self._n_frames)

    def _trigger_changed(self):
        pass

    @property
    def is_triggered(self):
        return self._triggered

    @property
    def trigger_area(self):
        if self.is_triggered:
            return self._resolution_area * self.trigger_options.area_fraction[1]
        else:
            return self._resolution_area * self.trigger_options.area_fraction[0]

    @property
    def trigger_threshold(self):
        if self.is_triggered:
            return self.trigger_options.threshold[1]
        else:
            return self.trigger_options.threshold[0]

    def _accum_new(self, data):
        if self.motion_accumulator is None:
            self.motion_accumulator = data
        else:
            self.motion_accumulator *= self.decay_factor
            self.motion_accumulator += data

    def _update_trigger_status(self):
        area_above_threshold = np.sum(self.motion_accumulator > self.trigger_threshold)
        new_triggered = (area_above_threshold >= self.trigger_area)
        # * TRIGGERED *
        if new_triggered != self._triggered:
            self._triggered = new_triggered
            self._trigger_changed()

    def process_motion_vector(self, a):
        self.processed_frames += 1
        t = process_time()
        # Record a new image
        self._accum_new(RatcamMD.compute_and_denoise_mv_norm(a))
        self._update_trigger_status()
        self.processing_time += process_time() - t


class LogDetector(RatcamMD, PiMotionAnalysis):
    def __init__(self, camera, size=None):
        RatcamMD.__init__(camera.resolution, int(camera.framerate))
        PiMotionAnalysis.__init(camera, size)

    def _trigger_changed(self):
        if self.is_triggered:
            print('Something is moving!')
        else:
            print('It stopped...')

    def analyze(self, a):
        self.process_motion_vector(a)


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
