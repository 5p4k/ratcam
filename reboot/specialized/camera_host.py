from ..plugins.base import PluginHost
from picamera import PiCamera
from picamera.array import PiMotionAnalysis
import Pyro4
import logging


_log = logging.getLogger('camera_host')


class _CameraPluginDispatcher(PiMotionAnalysis):
    def _dispatch(self, method_name, *args, **kwargs):
        for plugin_name, plugin_instance in self._camera_host.plugins.items():
            method = getattr(plugin_instance.camera, 'write')
            if method is not None:
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

    def __init__(self, camera_host):
        super(_CameraPluginDispatcher, self).__init__(self, camera_host.camera)
        self._camera_host = camera_host


class CameraHost(PluginHost):
    def __init__(self, *args, **kwargs):
        super(CameraHost, self).__init__(*args, **kwargs)
        self._camera = PiCamera()
        self._dispatcher = _CameraPluginDispatcher(self)
        self._bitrate = 750000

    def __enter__(self):
        super(CameraHost, self).__enter__()
        _log.info('Beginning streaming data at bitrate %s, framerate %s and resolution %s.',
                  str(self.bitrate), str(self.framerate), str(self.resolution))
        self.camera.start_recording(
            self._dispatcher,
            format='h264',
            motion_output=self._dispatcher,
            quality=None,
            bitrate=self.bitrate)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(CameraHost, self).__exit__(exc_type, exc_val, exc_tb)
        self.camera.stop_recording()
        _log.info('Stopping streaming data.')

    @Pyro4.expose
    @property
    def camera(self):
        return self._camera

    @property
    def framerate(self):
        return self.camera.framerate

    @framerate.setter
    def framerate(self, value):
        self.camera.framerate = value

    @property
    def resolution(self):
        return self.camera.resolution

    @resolution.setter
    def resolution(self, value):
        self.camera.resolution = value

    @property
    def bitrate(self):
        return self._bitrate

    @bitrate.setter
    def bitrate(self, value):
        if self.camera.recording:
            # TODO: possibly stop and restart recording?
            raise NotImplementedError('Unable to set bitrate while recording')
        else:
            self._bitrate = value

