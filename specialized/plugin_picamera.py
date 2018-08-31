from plugins.base import PluginProcessBase, Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin, active_plugins
from Pyro4 import expose as pyro_expose
import logging
from misc.logging import ensure_logging_setup
from misc.settings import SETTINGS


PICAMERA_PLUGIN_NAME = 'Picamera'
ensure_logging_setup()
_log = logging.getLogger(PICAMERA_PLUGIN_NAME.lower())


try:
    from picamera import PiCamera
    from picamera.array import PiMotionAnalysis
except (ImportError, OSError) as e:
    if isinstance(e, ImportError):
        _log.warning('Detected missing PiCamera package, running mockup.')
    else:
        _log.warning('Faulty PiCamera package (installed s/w else than a RPi?), running mockup.')

    class PiCamera:
        def __init__(self):
            self.recoding = False
            self.bitrate = 1
            self.framerate = 1
            self.resolution = (640, 480)  # Is this really the first resolution that comes to mind, in 2018?? :D

        def start_recording(self, *_, **__):
            self.recoding = True

        def stop_recording(self):
            self.recoding = False

    class PiMotionAnalysis:
        def __init__(self, _, __=None):
            pass


class CameraProcessBase(PluginProcessBase):
    @property
    def root_camera_plugin(self):
        return find_plugin(PICAMERA_PLUGIN_NAME).camera

    def write(self, data):
        pass

    def flush(self):
        pass

    def analyze(self, array):
        pass


def _cam_dispatch(self, method_name, *args, **kwargs):
    for plugin_name, plugin in active_plugins().items():
        # TODO Make sure it's ready to receive data
        if plugin.camera is None or not isinstance(plugin.camera, CameraProcessBase):
            continue
        method = getattr(plugin.camera, method_name, None)
        assert method is not None and callable(method), 'Calling a method undefined in CameraProcessBase?'
        try:
            method(*args, **kwargs)
        except Exception as exc:
            _log.error('Plugin %s has triggered an exception during %s: %s',
                       plugin_name, method_name, str(exc))


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


@make_plugin(PICAMERA_PLUGIN_NAME, Process.CAMERA)
class PicameraProcess(PluginProcessBase):
    def __init__(self):
        super(PicameraProcess, self).__init__()
        self._camera = PiCamera()
        self._bitrate = SETTINGS.camera.bitrate

    def __enter__(self):
        super(PicameraProcess, self).__enter__()
        _log.info('Beginning streaming data at bitrate %s, framerate %s and resolution %s.',
                  str(self.bitrate), str(self.framerate), str(self.resolution))
        self.camera.start_recording(
            _CameraPluginVideoDispatcher(),
            format='h264',
            motion_output=_CameraPluginMotionDispatcher(self.camera),
            quality=None,
            bitrate=self.bitrate)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(PicameraProcess, self).__exit__(exc_type, exc_val, exc_tb)
        self.camera.stop_recording()
        _log.info('Stopping streaming data.')

    @property
    def camera(self):
        return self._camera

    @pyro_expose
    @property
    def framerate(self):
        return self.camera.framerate

    @pyro_expose
    @framerate.setter
    def framerate(self, value):
        self.camera.framerate = value

    @pyro_expose
    @property
    def resolution(self):
        return self.camera.resolution

    @pyro_expose
    @resolution.setter
    def resolution(self, value):
        self.camera.resolution = value

    @pyro_expose
    @property
    def bitrate(self):
        return self._bitrate

    @pyro_expose
    @bitrate.setter
    def bitrate(self, value):
        if self.camera.recording:
            # TODO: possibly stop and restart recording?
            raise RuntimeError('Unable to set bitrate while recording')
        else:
            self._bitrate = value
