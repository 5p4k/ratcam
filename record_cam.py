from picamera import PiCamera
from misc.cam_replay import VideoRecorder, MotionRecorder, Recorder
from time import sleep
from misc.extended_json_codec import ExtendedJSONCodec
import argparse
import logging
import json
import os
import gzip


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


def resolution(txt):
    return tuple(list(map(int, txt.split('x')))[:2])


def format_size(sz):
    fmt = ['%0.0f B', '%0.0f KB', '%0.1f MB', '%0.2f GB', '%0.3f TB', '%0.3f PB', '%0.3f WTFB']
    idx = 0
    while sz > 1024.:
        sz = sz / 1024.
        idx += 1
    return fmt[idx] % sz


def main(args):
    camera = PiCamera()
    rec = Recorder(camera)
    vrec = VideoRecorder(rec)
    mrec = MotionRecorder(rec)
    camera.framerate = args.framerate
    camera.resolution = args.resolution
    logging.info('Starting warmup (2s). Recording %dx%d at %d fps, crf=%d.',
                 args.resolution[0], args.resolution[1], args.framerate, args.quality)
    camera.start_preview()
    sleep(2)
    logging.info('Will record (roughly) %d seconds.', args.duration)
    camera.start_recording(vrec, format='h264', motion_output=mrec, quality=26)
    try:
        sleep(args.duration)
        camera.stop_recording()
    except KeyboardInterrupt:
        camera.stop_recording()
    path = os.path.abspath(args.output.strip())
    logging.info('Collected %d events. Dumping to: %s', len(rec.data), path)
    if os.path.isfile(path):
        logging.warning('File %s exists! Moving to .old', path)
        os.rename(path, path + '.old')
    if path.lower().endswith('.gz'):
        logging.info('Automatically compressing with GZIP.')
        with gzip.open(path, 'wt') as fp:
            json.dump(rec.data, fp, cls=ExtendedJSONCodec, indent=2)
    else:
        logging.info('The file is mostly text and BASE64 binary data, it could be easily compressed.')
        logging.info('Just specify a .json.gz file in the argumets.')
        with open(args.output, 'w') as fp:
            json.dump(rec.data, fp, cls=ExtendedJSONCodec, indent=2)
    logging.info('Done, total file size: %s', format_size(os.path.getsize(path)))
    if args.mp4_output is not None:
        if os.path.isfile(args.mp4_output):
            logging.warning('File %s exists! Moving to .old', args.mp4_output)
            os.rename(path, path + '.old')
        try:
            with open(args.mp4_output, 'wb') as fp:
                vrec.dump_mp4(fp)
        except OSError as e:
            logging.error('Cannot write to %s, error: ', args.mp4_output, str(e))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', '-o', type=str, required=False, default='cam_replay.json.gz',
                        help='json[.gz] output file.')
    parser.add_argument('--mp4-output', '-v', type=str, required=False, default=None, help='Write also an mp4 here.')
    parser.add_argument('--resolution', '-r', default=(320, 240), type=resolution, required=False,
                        help='Resolution in pixels WxH')
    parser.add_argument('--duration', '-d', default=2., type=float, required=False, help='Duration in seconds.')
    parser.add_argument('--framerate', '-f', default=10, type=int, required=False,
                        help='Framerate in frames per second.')
    parser.add_argument('--quality', '-q', default=26, type=int, required=False, help='H.264 CRF quality.')
    main(parser.parse_args())
