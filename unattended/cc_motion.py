#!/usr/bin/env python3

from time import sleep
import numpy as np
import picamera
import picamera.array
from PIL import Image, ImageFilter

def median2d(a):
    med3x3 = np.vectorize(lambda i, j : np.median(
        a[(max(0, i - 1)):(min(a.shape[0], i + 2)),
          (max(0, j - 1)):(min(a.shape[1], j + 2))]
    ))
    return np.fromfunction(med3x3, a.shape, dtype=np.int)

def sq_norm(a):
    return np.interp(
        np.square(a['x'].astype(np.float)) + np.square(a['y'].astype(np.float)),
        (0, 128*128*2),
        (0, 255)
    ).astype(np.uint8)



if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (1920, 1080)
        camera.framerate = 30
        print('Warming up camera...')
        sleep(2)
        print('Recording...')
        with picamera.array.PiMotionArray(camera) as motion_stream:
            camera.start_recording('video.mp4', motion_output=motion_stream)
            camera.wait_recording(10)
            camera.stop_recording()
            for i in range(motion_stream.array.shape[0]):
                # img = Image.fromarray(median2d(sq_norm(motion_stream.array[i])).astype(np.uint8))
                img = Image.fromarray(sq_norm(motion_stream.array[i])).filter(ImageFilter.MedianFilter(size=3))
                filename = 'frame%03d.png' % i
                print('Writing %s' % filename)
                img.save(filename)
