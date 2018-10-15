from plugins.base import PluginProcessBase, Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin, active_plugins
from Pyro4 import expose as pyro_expose
import logging
from misc.logging import ensure_logging_setup, camel_to_snake
from misc.settings import SETTINGS
from time import sleep
from threading import Thread


_WARMUP_THREAD_TIME = 2.  # seconds
_WARMUP_THREAD_LEASE_TIME = _WARMUP_THREAD_TIME * 1.1

PICAMERA_ROOT_PLUGIN_NAME = 'PiCameraRoot'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(PICAMERA_ROOT_PLUGIN_NAME))


try:  # pragma: no cover
    from picamera import PiCamera
    from picamera.array import PiMotionAnalysis
except (ImportError, OSError) as e:  # pragma: no cover
    from misc.cam_replay import PiCameraMockup as PiCamera, PiMotionAnalysisMockup as PiMotionAnalysis
    if isinstance(e, ImportError):
        _log.warning('Detected missing PiCamera package, running mockup.')
    else:
        _log.warning('Faulty PiCamera package (installed s/w else than a RPi?), running mockup.')


class PiCameraProcessBase(PluginProcessBase):
    @classmethod
    def process(cls):  # pragma: no cover
        return Process.CAMERA

    def __init__(self):
        self._ready = False

    def __enter__(self):
        self._ready = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ready = False

    @property
    def ready(self):
        return self._ready

    @property
    def root_picamera_plugin(self):
        return find_plugin(PICAMERA_ROOT_PLUGIN_NAME).camera

    def write(self, data):  # pragma: no cover
        pass

    def flush(self):  # pragma: no cover
        pass

    def analyze(self, array):  # pragma: no cover
        pass


def _cam_dispatch(method_name, *args, **kwargs):
    for plugin_name, plugin in active_plugins().items():
        if plugin.camera is None or not isinstance(plugin.camera, PiCameraProcessBase):
            continue
        if not plugin.camera.ready:
            continue
        method = getattr(plugin.camera, method_name, None)
        assert method is not None and callable(method), 'Calling a method undefined in PiCameraProcessBase?'
        # noinspection PyBroadException
        try:
            method(*args, **kwargs)
        except:  # pragma: no cover
            _log.exception('Plugin %s has triggered an exception during %s.', plugin_name, method_name)


class _CameraPluginMotionDispatcher(PiMotionAnalysis):
    def analyze(self, array):
        _cam_dispatch('analyze', array)

    def __init__(self, camera):
        super(_CameraPluginMotionDispatcher, self).__init__(camera)


class _CameraPluginVideoDispatcher:
    def write(self, data):
        _cam_dispatch('write', data)

    def flush(self):
        _cam_dispatch('flush')


@make_plugin(PICAMERA_ROOT_PLUGIN_NAME, Process.CAMERA)
class PiCameraRootPlugin(PluginProcessBase):
    def __init__(self):
        super(PiCameraRootPlugin, self).__init__()
        self._camera = PiCamera()
        self._bitrate = SETTINGS.camera.bitrate
        self.framerate = SETTINGS.camera.framerate
        self._warmup_thread = Thread(target=self._warmup, name='PiCamera warmup thread')

    def __enter__(self):
        super(PiCameraRootPlugin, self).__enter__()
        self._warmup_thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(PiCameraRootPlugin, self).__exit__(exc_type, exc_val, exc_tb)
        self._warmup_thread.join(_WARMUP_THREAD_LEASE_TIME)
        if self._warmup_thread.is_alive():  # pragma: no cover
            _log.warning('The warmup thread did not join within %0.1fs.', _WARMUP_THREAD_LEASE_TIME)
            self._warmup_thread.join()
            _log.info('The warmup thread finally joined.')
        _log.info('Stopping streaming data...')
        self.camera.stop_recording()
        _log.info('Stopped')

    def _warmup(self):
        _log.info('Warming up (%0.fs).', _WARMUP_THREAD_TIME)
        self._camera.start_preview()
        sleep(_WARMUP_THREAD_TIME)
        _log.info('Beginning streaming data at bitrate %s, framerate %s and resolution %s.',
                  str(self.bitrate), str(self.framerate), str(self.resolution))
        self._camera.start_recording(
            _CameraPluginVideoDispatcher(),
            format='h264',
            motion_output=_CameraPluginMotionDispatcher(self.camera),
            quality=None,
            bitrate=self.bitrate)

    @property
    def camera(self):
        return self._camera

    @pyro_expose
    @property
    def framerate(self):
        return self.camera.framerate

    @pyro_expose
    @framerate.setter
    def framerate(self, value):  # pragma: no cover
        self.camera.framerate = value

    @pyro_expose
    @property
    def resolution(self):
        return self.camera.resolution

    @pyro_expose
    @resolution.setter
    def resolution(self, value):  # pragma: no cover
        self.camera.resolution = value

    @pyro_expose
    @property
    def bitrate(self):
        return self._bitrate

    @pyro_expose
    @bitrate.setter
    def bitrate(self, value):  # pragma: no cover
        if self.camera.recording:
            # TODO: possibly stop and restart recording?
            raise RuntimeError('Unable to set bitrate while recording')
        else:
            self._bitrate = value
