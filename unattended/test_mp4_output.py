#!/usr/bin/env python3
from mp4_helper import MP4Output
from time import sleep
import picamera

if __name__ == '__main__':
    with picamera.PiCamera() as camera:
        camera.resolution = (640, 480)
        camera.framerate = 15
        print('Warming up camera...')
        sleep(2)
        print('Recording...')
        with open('video.mp4', 'wb') as stream:
            with MP4Output(stream, camera) as mp4:
                camera.start_recording(mp4, format='h264')
                camera.wait_recording(2)
                camera.stop_recording()
