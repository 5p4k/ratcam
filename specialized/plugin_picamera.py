from plugins import PluginProcessBase, make_plugin, Process
from Pyro4 import expose as pyro_expose
import logging
from misc.settings import SETTINGS

try:
    from picamera import PiCamera
except ImportError:
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
try:
    from picamera.array import PiMotionAnalysis
except ImportError:
    class PiMotionAnalysis:
        pass


PICAMERA_PLUGIN_NAME = 'Picamera'
_log = logging.getLogger(PICAMERA_PLUGIN_NAME.lower())


class CameraProcessBase(PluginProcessBase):
    @property
    def camera_plugin(self):
        return self.plugins[PICAMERA_PLUGIN_NAME][Process.CAMERA]

    def write(self, data):
        pass

    def flush(self):
        pass

    def analyze(self, array):
        pass


class _CameraPluginDispatcher(PiMotionAnalysis):
    def _dispatch(self, method_name, *args, **kwargs):
        for plugin_name, plugin in self._picamera_proc.plugins.items():
            # TODO Make sure it's ready to receive data
            plugin_cam_process = plugin[Process.CAMERA]
            if plugin_cam_process is None:
                continue
            method = getattr(plugin_cam_process, method_name, None)
            if method is None or not callable(method):
                continue
            try:
                method(*args, **kwargs)
            except Exception as e:
                _log.error('Plugin %s has triggered an exception during %s: %s',
                           plugin_name, method_name, str(e))

    def write(self, data):
        self._dispatch('write', data)

    def flush(self):
        self._dispatch('flush')

    def analyze(self, array):
        self._dispatch('analyze', array)

    def __init__(self, picamera_proc):
        super(_CameraPluginDispatcher, self).__init__(self, picamera_proc.camera)
        self._picamera_proc = picamera_proc


@make_plugin(PICAMERA_PLUGIN_NAME, Process.CAMERA)
class PicameraProcess(PluginProcessBase):
    def __init__(self):
        super(PicameraProcess, self).__init__()
        self._camera = PiCamera()
        self._bitrate = SETTINGS.camera.bitrate
        self._dispatcher = _CameraPluginDispatcher(self)

    def __enter__(self):
        super(PicameraProcess, self).__enter__()
        _log.info('Beginning streaming data at bitrate %s, framerate %s and resolution %s.',
                  str(self.bitrate), str(self.framerate), str(self.resolution))
        self.camera.start_recording(
            self._dispatcher,
            format='h264',
            motion_output=self._dispatcher,
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
            raise NotImplementedError('Unable to set bitrate while recording')
        else:
            self._bitrate = value
