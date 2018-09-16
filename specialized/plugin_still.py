from plugins.base import Process, PluginProcessBase
from plugins.decorators import make_plugin
from specialized.plugin_media_manager import MEDIA_MANAGER_PLUGIN_NAME
from specialized.plugin_picamera import PICAMERA_ROOT_PLUGIN_NAME
from plugins.processes_host import find_plugin
from Pyro4 import expose as pyro_expose
import logging
from misc.logging import ensure_logging_setup, camel_to_snake
from misc.settings import SETTINGS
from threading import Thread, Event
from queue import Queue
from tempfile import NamedTemporaryFile
import os


STILL_PLUGIN_NAME = 'Still'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(STILL_PLUGIN_NAME))


@make_plugin(STILL_PLUGIN_NAME, Process.CAMERA)
class StillPlugin(PluginProcessBase):
    def __init__(self):
        self._jpeg_quality = SETTINGS.camera.jpeg_quality
        self._still_thread = None
        self._still_thread_queue = None
        self._still_thread_wake = Event()
        self._still_thread_stop = Event()

    def __enter__(self):
        self._still_thread_queue = Queue()
        self._still_thread_wake.clear()
        self._still_thread_stop.clear()
        self._still_thread = Thread(target=self._still_thread_main, name='take_still_pic_thread')
        self._still_thread.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._still_thread_stop.set()
        self._still_thread_wake.set()
        self._still_thread.join(1.)
        if self._still_thread.is_alive():  # pragma: no cover
            _log.warning('The still picture thread did not join within 1s.')
            self._still_thread.join()
            _log.info('The still picture thread finally joined.')

    @pyro_expose
    @property
    def jpeg_quality(self):
        return self._jpeg_quality

    @pyro_expose
    @jpeg_quality.setter
    def jpeg_quality(self, value):
        self._jpeg_quality = max(0.0, value)

    def _still_thread_main(self):
        while not self._still_thread_stop.is_set():
            self._still_thread_wake.wait()
            self._still_thread_wake.clear()
            while not self._still_thread_queue.empty() and not self._still_thread_stop.is_set():
                info = self._still_thread_queue.get_nowait()
                camera = find_plugin(PICAMERA_ROOT_PLUGIN_NAME).camera
                if camera is None:
                    _log.error('No %s is running on CAMERA! Will not take a still with info %s.',
                               PICAMERA_ROOT_PLUGIN_NAME, str(info))
                    continue
                with NamedTemporaryFile(delete=False) as temp_file:
                    media_path = temp_file.name
                    _log.info('Taking still picture with info %s to %s.', str(info), media_path)
                    camera.camera.capture(media_path, format='jpeg', use_video_port=True, quality=self.jpeg_quality)
                    temp_file.flush()
                    temp_file.close()
                media_mgr = find_plugin(MEDIA_MANAGER_PLUGIN_NAME, Process.CAMERA)
                if media_mgr is None:
                    _log.error('Could not find a media manager on the CAMERA thread.')
                    _log.warning('Discarding media with info %s at %s', str(info), media_path)
                    try:
                        os.remove(media_path)
                    except OSError as e:
                        _log.error('Could not delete %s, error: %s', media_path, e.strerror)
                else:
                    media = media_mgr.deliver_media(media_path, 'jpeg', info)
                    _log.info('Dispatched media %s with info %s at %s.', str(media.uuid), str(media.info), media.path)

    @pyro_expose
    def take_picture(self, info=None):
        _log.info('Requested media with info %s', str(info))
        self._still_thread_queue.put(info)
        self._still_thread_wake.set()
