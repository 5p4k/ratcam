#!/usr/bin/env python3
import numpy as np
import picamera
import picamera.array
import time
from PIL import Image, ImageFilter
from time import process_time

NUMPY_TIME = 0.
PIL_TIME = 0.
N_FRAMES = 0

def quick_median(a):
    global N_FRAMES
    N_FRAMES +=1
    img = Image.fromarray(a).filter(ImageFilter.MedianFilter(size=3))
    # img.save('frame%04d.png' % N_FRAMES)
    return np.array(img.getdata())

class DetectMotion(picamera.array.PiMotionAnalysis):
    def analyze(self, a):
        global NUMPY_TIME
        global PIL_TIME
        t_start = process_time()
        a = np.interp(
            np.sqrt(np.square(a['x'].astype(np.uint16)) + np.square(a['y'].astype(np.uint16))),
            (0, 182),
            (0, 255)
        ).astype(np.uint8)
        NUMPY_TIME += process_time() - t_start
        t_start = process_time()
        a  = quick_median(a)
        PIL_TIME += process_time() - t_start
        t_start = process_time()
        # If there're more than 10 vectors with a magnitude greater
        # than 60, then say we've detected motion
        if (a > 60).sum() > 10:
            print('Motion detected! %d' % int(time.time() * 1000))
        NUMPY_TIME += process_time() - t_start

with picamera.PiCamera() as camera:
    with DetectMotion(camera) as output:
        camera.resolution = (1920, 1080)
        print('Starting...')
        camera.framerate = 30
        camera.start_recording(
              'video.mp4', format='mp4', motion_output=output)
        try:
            camera.wait_recording(30)
        except KeyboardInterrupt:
            pass
        camera.stop_recording()

print('Total time spent in numpy:', NUMPY_TIME)
print('Total time spent in PIL:', PIL_TIME)
print('Number of frames analysed:', N_FRAMES)

print('Average frame processing time:', (NUMPY_TIME + PIL_TIME) / N_FRAMES)
print('Maximum avg fps achievable:', N_FRAMES / (NUMPY_TIME + PIL_TIME))