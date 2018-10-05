from plugins.base import Process, PluginProcessBase
from plugins.decorators import make_plugin
from specialized.plugin_media_manager import MEDIA_MANAGER_PLUGIN_NAME, MediaReceiver
from specialized.plugin_still import STILL_PLUGIN_NAME
from specialized.plugin_picamera import PICAMERA_ROOT_PLUGIN_NAME
from specialized.plugin_buffered_recorder import BUFFERED_RECORDER_PLUGIN_NAME
from specialized.plugin_motion_detector import MOTION_DETECTOR_PLUGIN_NAME, MotionDetectorResponder
from specialized.plugin_telegram import TELEGRAM_PLUGIN_NAME, TelegramProcessBase, handle_command, handle_message


@make_plugin('Ratcam', Process.TELEGRAM)
class RatcamTelegramPlugin(TelegramProcessBase, MediaReceiver):
    def handle_media(self, media):
        pass


@make_plugin('Ratcam', Process.CAMERA)
class RatcamCameraPlugin(PluginProcessBase):
    pass


@make_plugin('Ratcam', Process.MAIN)
class RatcamMainPlugin(PluginProcessBase, MotionDetectorResponder):
    def _motion_status_changed_internal(self, is_moving):
        pass
