#!/usr/bin/env python3
from time import sleep
import picamera

if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (640, 480)
        camera.framerate = 15
        print('Warming up camera...')
        sleep(2)
        print('Recording...')
        camera.start_recording('video.mp4')
        camera.wait_recording(2)
        camera.stop_recording()

