from plugins.base import Process, PluginProcessBase
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin
from specialized.plugin_media_manager import MediaReceiver, Media
from specialized.plugin_still import StillPlugin
from specialized.plugin_picamera import PiCameraRootPlugin
from specialized.plugin_buffered_recorder import BufferedRecorderPlugin
from specialized.plugin_motion_detector import MotionDetectorResponder, MotionDetectorCameraPlugin
from specialized.plugin_telegram import TelegramProcessBase, handle_command, TelegramRootPlugin
from specialized.plugin_pwmled import PWMLedPlugin
import os
import logging
from misc.logging import camel_to_snake
from misc.settings import SETTINGS
from Pyro4 import expose as pyro_expose
from specialized.support.txtutils import fuzzy_bool, bool_desc, user_desc
import telegram


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


class KnownPluginsCache:
    def __init__(self):
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
                TelegramRootPlugin: find_plugin(TelegramRootPlugin, Process.TELEGRAM),
                PWMLedPlugin: find_plugin(PWMLedPlugin, Process.MAIN)
            }

    def _clear_plugins_cache(self):
        self._plugins_cache_outdated = True

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
    def pwm_led_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[PWMLedPlugin]

    @property
    def still_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[StillPlugin]

    @property
    def root_picamera_plugin(self):
        self._ensure_plugins_cache()
        return self._plugins_cache[PiCameraRootPlugin]


@make_plugin(RATCAM_PLUGIN_NAME, Process.TELEGRAM)
class RatcamTelegramPlugin(TelegramProcessBase, MediaReceiver, MotionDetectorResponder, KnownPluginsCache):
    def __enter__(self):
        super(RatcamTelegramPlugin, self).__enter__()
        self._clear_plugins_cache()

    def _enum_recipient_chat_ids(self, info):
        if info is None:
            yield from self.root_telegram_plugin.authorized_chat_ids
        elif isinstance(info, telegram.Update):
            yield info.effective_chat.id

    @property
    def motion_detection_enabled(self):
        counterpart = find_plugin(self, Process.MAIN)
        if counterpart is None:
            _log.error('Cannot find the main Ratcam process.')
            return False
        return counterpart.motion_detection_enabled

    @motion_detection_enabled.setter
    def motion_detection_enabled(self, value):
        counterpart = find_plugin(self, Process.MAIN)
        if counterpart is None:
            _log.error('Cannot find the main Ratcam process.')
        else:
            counterpart.motion_detection_enabled = value

    @property
    def is_recording_manually(self):
        counterpart = find_plugin(self, Process.MAIN)
        if counterpart is None:
            _log.error('Cannot find the main Ratcam process.')
            return False
        return counterpart.is_recording_manually

    def set_manual_recording(self, value=True):
        counterpart = find_plugin(self, Process.MAIN)
        if counterpart is None:
            _log.error('Cannot find the main Ratcam process.')
        else:
            counterpart.set_manual_recording(value)

    @handle_command('detect', pass_args=True)
    def cmd_detect(self, upd, args):
        if len(args) not in (0, 1):
            return  # More than one argument is not something we handle
        if self.motion_detector_plugin is None:
            self.root_telegram_plugin.reply_message(upd, 'Cannot offer motion detection, the %s is not loaded.' %
                                                    MotionDetectorCameraPlugin.plugin_name())
            return
        if len(args) == 0:
            self.root_telegram_plugin.reply_message(upd, 'Motion detection is %s.' %
                                                    bool_desc(self.motion_detection_enabled))
        else:
            try:
                enable = fuzzy_bool(args[0])
                if enable:
                    if self.motion_detection_enabled:
                        self.root_telegram_plugin.reply_message(upd, 'Motion detection is already on.')
                    else:
                        self.motion_detection_enabled = True
                        _log.info('[%s] turned detection on.', user_desc(upd))
                        self.root_telegram_plugin.reply_message(upd, 'Motion detection was turned on.')

                else:
                    if self.motion_detection_enabled:
                        self.motion_detection_enabled = False
                        self.root_telegram_plugin.reply_message(upd, 'Motion detection was turned off.')
                        _log.info('[%s] turned detection off.', user_desc(upd))
                    else:
                        self.root_telegram_plugin.reply_message(upd, 'Motion detection is already off.')
            except ValueError:
                self.root_telegram_plugin.reply_message(upd, 'Please specify \'on\' or \'off\' or nothing.')

    @handle_command('light', pass_args=True)
    def cmd_detect(self, upd, args):
        if len(args) not in (0, 1):
            return  # More than one argument is not something we handle
        if self.pwm_led_plugin is None:
            self.root_telegram_plugin.reply_message(upd, 'Cannot offer LED light, the %s is not loaded.' %
                                                    PWMLedPlugin.plugin_name())
            return
        elif self.pwm_led_plugin.bcm_pin is None:
            self.root_telegram_plugin.reply_message(upd, 'Cannot offer LED light, pin number not set.')
            return
        if len(args) == 0:
            light_value = self.pwm_led_plugin.value
            self.root_telegram_plugin.reply_message(upd, 'Light is %s (set at %d%%).' %
                                                    (bool_desc(light_value > 0), int(100. * light_value)))
        elif args[0].strip().lower() in ['pulse', 'test']:
            self.root_telegram_plugin.reply_message(upd, 'Will pulse the light for testing purposes.')
            _log.info('[%s] requested to pulse the light.', user_desc(upd))
            self.pwm_led_plugin.pulse()
        else:
            # Try a float first
            light_value = None
            try:
                light_value = float(args[0])
            except ValueError:
                try:
                    # Try a bool then
                    if fuzzy_bool(args[0]):
                        light_value = 1.
                    else:
                        light_value = 0.
                except ValueError:
                    self.root_telegram_plugin.reply_message(upd, 'Please specify \'on\' or \'off\' or a valid number.')
                    return
            if light_value == self.pwm_led_plugin.value:
                self.root_telegram_plugin.reply_message(upd, 'Light is already set to %d%%.' % int(100. * light_value))
            else:
                self.pwm_led_plugin.value = light_value
                _log.info('[%s] set the light to %d%%.', user_desc(upd), int(100. * light_value))
                self.root_telegram_plugin.reply_message(upd, 'Setting light to %d%%.' % int(100. * light_value))

    @handle_command('photo')
    def cmd_photo(self, upd):
        if self.still_plugin is None:
            self.root_telegram_plugin.reply_message(upd, 'Cannot take a picture, %s is not loaded.' %
                                                    StillPlugin.plugin_name())
        else:
            _log.info('[%s] requested a photo.', user_desc(upd))
            self.still_plugin.take_picture(info=upd)

    @handle_command('video')
    def cmd_video(self, upd):
        if self.buffered_recorder_plugin is None:
            self.root_telegram_plugin.reply_message(upd, 'Cannot take a video, %s is not loaded.' %
                                                    BufferedRecorderPlugin.plugin_name())
        else:
            _log.info('[%s] requested a video.', user_desc(upd))
            self.set_manual_recording()
            self.buffered_recorder_plugin.record(info=upd, stop_after_seconds=SETTINGS.ratcam.get(
                'video_duration', cast_to_type=float, ge=1., le=60., default=8.))

    def handle_media(self, media):
        if self.root_telegram_plugin is None or not os.path.isfile(media.path):
            return
        known_kind, media = _patch_media_kind(media)
        if not known_kind:
            _log.warning('Unrecognized media type %s.', media.kind)
            return
        recipients = self._enum_recipient_chat_ids(media.info)
        # noinspection PyBroadException
        try:
            with open(media.path, 'rb') as fp:
                if media.kind in _KNOWN_PHOTO_KINDS:
                    self.root_telegram_plugin.broadcast_photo(recipients, fp, timeout=SETTINGS.telegram.get(
                        'photo_timeout', cast_to_type=float, ge=5., default=20.))
                elif media.kind in _KNOWN_VIDEO_KINDS:
                    self.root_telegram_plugin.broadcast_video(recipients, fp, timeout=SETTINGS.telegram.get(
                        'video_timeout', cast_to_type=float, ge=5., default=60.))
        except OSError:
            _log.exception('Could not load media file %s.', str(media.uuid))
        except:
            _log.exception('Error when sending media %s.', str(media.uuid))

    def _motion_status_changed_internal(self, is_moving):
        if self.root_telegram_plugin is None or not self.motion_detection_enabled:
            return
        if is_moving:
            self.root_telegram_plugin.broadcast_message(self.root_telegram_plugin.authorized_chat_ids,
                                                        'Something is moving...')
        else:
            self.root_telegram_plugin.broadcast_message(self.root_telegram_plugin.authorized_chat_ids,
                                                        'Everything quiet.')


@make_plugin(RATCAM_PLUGIN_NAME, Process.MAIN)
class RatcamMainPlugin(PluginProcessBase, MotionDetectorResponder, KnownPluginsCache):
    def __init__(self):
        super(RatcamMainPlugin, self).__init__()
        self._motion_detection_enabled = False
        self._manual_recording = False

    def __enter__(self):
        super(RatcamMainPlugin, self).__enter__()
        self._clear_plugins_cache()

    @pyro_expose
    @property
    def is_recording_manually(self):
        return self.is_recording and self._manual_recording

    @pyro_expose
    def set_manual_recording(self, manual=True):
        self._manual_recording = manual

    @pyro_expose
    @property
    def is_recording(self):
        return self.buffered_recorder_plugin is not None and self.buffered_recorder_plugin.is_recording

    @pyro_expose
    @property
    def motion_detection_enabled(self):
        return self._motion_detection_enabled

    @pyro_expose
    @motion_detection_enabled.setter
    def motion_detection_enabled(self, enabled):
        if self.motion_detector_plugin is None:
            _log.warning('Attempt to change motion detection with no %s.' % MotionDetectorCameraPlugin.plugin_name())
            return
        if not self._motion_detection_enabled and enabled and self.motion_detector_plugin.triggered:
            self._motion_detection_enabled = True
            for plugin_instance in find_plugin(self).nonempty_values():
                plugin_instance.motion_status_changed(True)
        elif self._motion_detection_enabled and not enabled and self.motion_detector_plugin.triggered:
            for plugin_instance in find_plugin(self).nonempty_values():
                plugin_instance.motion_status_changed(False)
            self._motion_detection_enabled = False
        else:
            self._motion_detection_enabled = enabled

    def _motion_status_changed_internal(self, is_moving):
        if not self.motion_detection_enabled:
            return
        assert self.motion_detector_plugin is not None
        if is_moving:
            self.motion_detector_plugin.take_motion_picture()
        if self.buffered_recorder_plugin is not None:
            if self.is_recording and not is_moving and not self.is_recording_manually:
                self.buffered_recorder_plugin.stop_and_finalize()
            elif not self.is_recording and is_moving:
                self.set_manual_recording(False)
                self.buffered_recorder_plugin.record()
