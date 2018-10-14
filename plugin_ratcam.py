from plugins.base import Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin
from specialized.plugin_media_manager import MediaReceiver, Media
from specialized.plugin_still import StillPlugin
from specialized.plugin_picamera import PiCameraRootPlugin
from specialized.plugin_buffered_recorder import BufferedRecorderPlugin
from specialized.plugin_motion_detector import MotionDetectorResponder, MotionDetectorCameraPlugin
from specialized.plugin_telegram import TelegramProcessBase, handle_command, TelegramRootPlugin
import os
import logging
from misc.logging import camel_to_snake
from misc.settings import SETTINGS
from Pyro4 import expose as pyro_expose


RATCAM_PLUGIN_NAME = 'Ratcam'
_log = logging.getLogger(camel_to_snake(RATCAM_PLUGIN_NAME))

_KNOWN_PHOTO_KINDS = ['jpg', 'jpeg']
_KNOWN_VIDEO_KINDS = ['mp4']

_KNOWN_MEDIA_KINDS = _KNOWN_PHOTO_KINDS + _KNOWN_VIDEO_KINDS


def _patch_media_kind(media):
    kind = media.kind.lower()
    if kind not in _KNOWN_MEDIA_KINDS:
        return False, media
    return True, Media(media.uuid, media.owning_process, kind, media.path, media.info)


@make_plugin(RATCAM_PLUGIN_NAME, Process.TELEGRAM)
class RatcamTelegramPlugin(TelegramProcessBase, MediaReceiver, MotionDetectorResponder):
    def __init__(self):
        super(RatcamTelegramPlugin, self).__init__()
        self._motion_detection_enabled = False
        self._manual_recording = False
        self._plugins_cache_outdated = True
        self._plugins_cache = None

    def _ensure_plugins_cache(self):
        if self._plugins_cache_outdated:
            self._plugins_cache_outdated = False
            self._plugins_cache = {
                BufferedRecorderPlugin: find_plugin(BufferedRecorderPlugin, Process.CAMERA),
                MotionDetectorCameraPlugin: find_plugin(MotionDetectorCameraPlugin, Process.CAMERA),
                PiCameraRootPlugin: find_plugin(PiCameraRootPlugin, Process.CAMERA),
                StillPlugin: find_plugin(StillPlugin, Process.CAMERA),
                TelegramRootPlugin: find_plugin(TelegramRootPlugin, Process.TELEGRAM)
            }

    @property
    def buffered_recorder_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[BufferedRecorderPlugin]

    @property
    def root_telegram_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[TelegramRootPlugin]

    @property
    def motion_detector_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[MotionDetectorCameraPlugin]

    @property
    def still_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[StillPlugin]

    @property
    def root_picamera_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[PiCameraRootPlugin]

    def __enter__(self):
        super(RatcamTelegramPlugin, self).__enter__()
        self._plugins_cache_outdated = True

    @pyro_expose
    @property
    def motion_detection_enabled(self):
        return self._motion_detection_enabled

    @pyro_expose
    @motion_detection_enabled.setter
    def motion_detection_enabled(self, enabled):
        if self._motion_detection_enabled and not enabled:
            if self.buffered_recorder_plugin is not None and self.buffered_recorder_plugin.is_recording:
                self.buffered_recorder_plugin.stop_and_discard()
        elif enabled and self.motion_detector_plugin.triggered:
            # Fetch the status and trigger
            self.motion_status_changed(True)
        self._motion_detection_enabled = enabled

    @pyro_expose
    @property
    def is_recording_manually(self):
        return self.is_recording and self._manual_recording

    @pyro_expose
    @property
    def is_recording(self):
        return self.buffered_recorder_plugin is not None and self.buffered_recorder_plugin.is_recording

    @staticmethod
    def _photo_timeout():
        return max(SETTINGS.telegram.photo_timeout, 5.)

    @staticmethod
    def _video_timeout():
        return max(SETTINGS.telegram.video_timeout, 5.)

    def _enum_recipient_chat_ids(self, _):
        yield from self.root_telegram_plugin.authorized_chat_ids

    def handle_media(self, media):
        if not os.path.isfile(media.path):
            return
        known_kind, media = _patch_media_kind(media)
        if not known_kind:
            _log.warning('Unrecognized media type %s.', media.kind)
            return
        recipients = self._enum_recipient_chat_ids(media.info)
        try:
            if media.kind in _KNOWN_PHOTO_KINDS:
                self.root_telegram_plugin.broadcast_photo(recipients, media.path,
                                                          timeout=RatcamTelegramPlugin._photo_timeout())
            elif media.kind in _KNOWN_VIDEO_KINDS:
                self.root_telegram_plugin.broadcast_video(recipients, media.path,
                                                          timeout=RatcamTelegramPlugin._video_timeout())
        except OSError as e:
            _log.error('Could not load media file %s, error: %s', str(media.uuid), e.strerror)
        except Exception as e:
            _log.error('Error when sending media %s: %s', str(media.uuid), str(e))

    def _motion_status_changed_internal(self, is_moving):
        if self.motion_detection_enabled:
            if is_moving:
                self.root_telegram_plugin.broadcast_message('Something is moving...')
                self.motion_detector_plugin.take_motion_picture()
            else:
                self.root_telegram_plugin.broadcast_message('Everything quiet.')
            if self.buffered_recorder_plugin is not None:
                if self.buffered_recorder_plugin.is_recording and not is_moving and not self.is_recording_manually:
                    self.buffered_recorder_plugin.stop_and_finalize()
                elif not self.buffered_recorder_plugin.is_recording and is_moving:
                    self._manual_recording = False
                    self.buffered_recorder_plugin.record()
