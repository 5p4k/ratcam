from cam_manager import CameraManager, CameraMode
from misc import log
from telegram.ext import Updater, CommandHandler
import io

class RatcamBot:

    def _bot_start(self, bot, update):
        log().info('Ratcam bot started by user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)

        bot.send_message(chat_id=update.message.chat_id, text='Ratcam SimpleBot active.')


    def _bot_photo(self, bot, update):
        log().info('A picture is going to be taken for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)

        self._cam_mgr.mode = CameraMode.PHOTO
        with io.BytesIO() as stream:
            self._cam_mgr.cam.capture(stream, 'jpeg')
            stream.seek(0)
            bot.send_photo(chat_id=update.message.chat_id, photo=stream)


    def _bot_video(self, bot, update):
        log().info('A video is going to be recorder for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)

        self._cam_mgr.mode = CameraMode.VIDEO
        with io.BytesIO() as stream:
            self._cam_mgr.start_recording(stream, format='h264', quality=23)
            self._cam_mgr.wait_recording(8)
            stream.seek(0)
            bot.send_video(chat_id=update.message.chat_id, video=stream)


    def work(self):
        self._updater.start_polling()
        self._updater.idle()


    def __init__(self, token):
        self._cam_mgr = CameraManager()
        self._updater = Updater(token=token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self._bot_start))
        self._updater.dispatcher.add_handler(CommandHandler('photo', self._bot_photo))
        self._updater.dispatcher.add_handler(CommandHandler('video', self._bot_video))
