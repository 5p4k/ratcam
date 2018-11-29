import argparse
import logging
from misc.settings import SETTINGS
from plugins.decorators import get_all_plugins
from specialized import plugin_telegram, plugin_picamera, plugin_motion_detector, plugin_buffered_recorder, \
    plugin_still, plugin_media_manager, plugin_status_led, plugin_pwmled
import plugin_ratcam
from plugins.processes_host import ProcessesHost
from misc.logging import ensure_logging_setup
from misc.signal import GracefulSignal


ensure_logging_setup()


def main(args):
    if args.token:
        SETTINGS.telegram.token = args.token
    if args.logfile is not None:
        ensure_logging_setup(logging.DEBUG if args.verbose else logging.INFO, reset=True, filename=args.logfile)
    else:
        ensure_logging_setup(logging.DEBUG if args.verbose else logging.INFO, reset=True)

    plugins = get_all_plugins()
    assert plugin_telegram.TELEGRAM_ROOT_PLUGIN_NAME in plugins
    assert plugin_picamera.PICAMERA_ROOT_PLUGIN_NAME in plugins
    assert plugin_media_manager.MEDIA_MANAGER_PLUGIN_NAME in plugins
    assert plugin_buffered_recorder.BUFFERED_RECORDER_PLUGIN_NAME in plugins
    assert plugin_motion_detector.MOTION_DETECTOR_PLUGIN_NAME in plugins
    assert plugin_still.STILL_PLUGIN_NAME in plugins
    assert plugin_ratcam.RATCAM_PLUGIN_NAME in plugins
    assert plugin_pwmled.PWMLED_PLUGIN_NAME in plugins
    assert plugin_status_led.STATUS_LED_PLUGIN_NAME in plugins
    if not args.camera:
        del plugins[plugin_picamera.PICAMERA_ROOT_PLUGIN_NAME]
    if not args.light:
        del plugins[plugin_pwmled.PWMLED_PLUGIN_NAME]
    if not args.status_led:
        del plugins[plugin_status_led.STATUS_LED_PLUGIN_NAME]
    logging.info('Running the following plugins: ' + ', '.join(plugins.keys()))
    # Ignore KeyboardInterrupt. If we don't do so, it will be raised also in the child processes. We do not have control
    # over the threads running in the child processes, so they will terminate, and here we get some network exception
    # because the socket is closed. We want instead to terminate gracefully.
    with GracefulSignal() as sigint:
        with ProcessesHost(plugins):
            logging.info('Ready.')
            sigint.wait()
            logging.info('Turning off...')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', '-t', required=False, help='Telegram chat token.')
    parser.add_argument('--no-cam', '--no-camera', '-nc', required=False, dest='camera', default=True,
                        action='store_false', help='Skip initializing camera plugin.')
    parser.add_argument('--no-status', '--no-status-led', required=False, dest='status_led', default=True,
                        action='store_false', help='Skip initializing status LED plugin.')
    parser.add_argument('--no-light', '-nl', required=False, dest='light', default=True, action='store_false',
                        help='Skip PWM controlled led light.')
    parser.add_argument('--verbose', '-v', required=False, default=False, action='store_true',
                        help='Log up to debug level')
    parser.add_argument('--logfile', '--log', dest='logfile', required=False, default=None,
                        help='Log everything to a file.')
    main(parser.parse_args())
