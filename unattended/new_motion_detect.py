#!/usr/bin/env python3
import numpy as np
from picamera import PiCamera
from picamera.array import PiMotionAnalysis
from PIL import Image, ImageFilter, ImageChops
from collections import namedtuple
from time import process_time

TriggerOptions = namedtuple('TriggerOptions', ['threshold', 'area_fraction'])

DEFAULT_TRIGGER_OPTIONS = TriggerOptions(threshold=(15000, 10000), area_fraction=(1e-3, 5e-4))

class RatcamMD(PiMotionAnalysis):

    @staticmethod
    def compute_norm(a, max_output=65535, dtype=np.uint16):
        # Need to use uint16 to avoid overflow. Also seems faster than float and uint32
        return np.interp(
            np.sqrt(np.square(a['x']).astype(np.uint16) + np.square(a['y']).astype(np.uint16)),
            (0, 182), # x and y are 8bit signed, that is, max norm is sqrt(2) * 128
            (0, max_output)
        ).astype(dtype)

    @staticmethod
    def norm_to_img(a, median_size=3):
        retval = Image.fromarray(a)
        if median_size > 1:
            retval = retval.filter(ImageFilter.MedianFilter(size=median_size))
        return retval

    def __init__(self, camera, size=None):
        super(self, RatcamMD).__init__(camera, size)
        self.n_frames = int(camera.framerate)
        self.trigger_options = DEFAULT_TRIGGER_OPTIONS
        self.history = []
        self.state = None
        self._triggered = False
        assert(len(self.trigger_options.threshold) == 2)
        assert(self.trigger_options.threshold[0] >= self.trigger_options.threshold[1])
        assert(len(self.trigger_options.area_fraction) == 2)
        assert(self.trigger_options.area_fraction[0] >= self.trigger_options.area_fraction[1])
        self.processed_frames = 0
        self.processing_time = 0.

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
        # First step
        if self.state is None:
            self.state = new_image
            return
        if len(self.history) > self.n_frames:
            # Remove the oldest and subtract
            self.state = ImageChops.difference(self.state, self.history[0])
            del self.history[0]
        # Add the new one
        self.state = ImageChops.add(self.state, new_image)

    def _update_trigger_status(self):
        area_above_threshold = count_above_threshold(self.state, self.trigger_threshold)
        new_triggered = (area_above_threshold >= self.trigger_area)
        # * TRIGGERED *
        if new_triggered != self._triggered:
            self._triggered = new_triggered
            self._trigger_changed()

    def analyze(self, a):
        self.processed_frames += 1
        max_output = 65535 // self.n_frames
        t = process_time()
        # Record a new image
        self._accum_new(norm_to_img(compute_norm(a, max_output)))
        self._update_trigger_status()
        self.processing_time += t - process_time()


class LogDetector(RatcamMD):
    def _trigger_changed(self):
        if self.is_triggered:
            print('Something is moving!')
        else:
            print('It stopped...')


with PiCamera() as camera:
    camera.resolution = (1920, 1080)
    camera.framerate = 30
    with LogDetector(camera) as output:
        print('Starting...')
        camera.start_recording('video.mp4', format='mp4', motion_output=output)
        try:
            camera.wait_recording(30)
        except KeyboardInterrupt:
            pass
        print('Stopping...')
        camera.stop_recording()
        print('Total processing time (s):', output.processing_time)
        print('Number of frame processed:', output.processed_frames)
        print('Maximum average achievable fps:', output.processed_frames / output.processing_time)
