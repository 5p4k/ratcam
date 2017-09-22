#
# Copyright (C) 2017  Pietro Saccardi

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from telegram.ext import Updater, CommandHandler
import os
import logging

_log = logging.getLogger('ratcam')

YES = ['y', 'yes', '1', 'on', 't', 'true']
NO = ['n', 'no', '0', 'off', 'f', 'false']

BOT_PHOTO_TIMEOUT = 20
BOT_VIDEO_TIMEOUT = 60


def human_file_size(file_name, suffix='B'):
    sz = os.path.getsize(file_name)
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(sz) < 1000.0:
            return "%3.1f%s%s" % (sz, unit, suffix)
        sz /= 1000.0
    return "%.1f%s%s" % (sz, 'Y', suffix)


class BotManager:
    def _bot_start(self, bot, update):
        if self.chat_id is not None:
            return
        _log.info('Bot: started by user %s, %s (%s)',
                  update.message.from_user.first_name,
                  update.message.from_user.last_name,
                  update.message.from_user.username)
        self.chat_id = update.message.chat_id
        if self.chat_id:
            bot.send_message(chat_id=self.chat_id, text='Ratcam SimpleBot active.')

    def _bot_detect(self, bot, update, args):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        switch = args[0].strip().lower()
        if switch not in YES and switch not in NO:
            bot.send_message(chat_id=self.chat_id, text='I did not understand.',
                             reply_to_message_id=update.message.message_id)
            return
        if switch in YES:
            self._cam_interface.toggle_detection(True)
        elif switch in NO:
            self._cam_interface.toggle_detection(False)

    def _bot_photo(self, _, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        _log.info('Bot: taking photo for %s, %s (%s)',
                  update.message.from_user.first_name,
                  update.message.from_user.last_name,
                  update.message.from_user.username)
        self._cam_interface.request_photo()

    def _bot_video(self, _, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        _log.info('Bot: taking video for %s, %s (%s)',
                  update.message.from_user.first_name,
                  update.message.from_user.last_name,
                  update.message.from_user.username)
        self._cam_interface.request_video()

    def __enter__(self):
        self._updater.start_polling(clean=True)
        _log.info('Bot: enter.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        _log.info('Bot: exit.')

    def send_media(self, file_name, media_type):
        if self.chat_id:
            try:
                _log.info('Bot: sending media %s (%s)' % (file_name, human_file_size(file_name)))
                with open(file_name, 'rb') as file:
                    if media_type == 'mp4':
                        self._updater.bot.send_video(chat_id=self.chat_id, video=file, timeout=BOT_VIDEO_TIMEOUT)
                    elif media_type == 'jpeg':
                        self._updater.bot.send_photo(chat_id=self.chat_id, photo=file, timeout=BOT_PHOTO_TIMEOUT)
            except Exception as e:
                _log.error(str(e))
                # Can't do any better logging,  because everything is hidden behind Telegram
                # exceptions [1]
                xcp_text = 'Could not send %s (%s); exception: "%s".' % \
                           (media_type, human_file_size(file_name), str(e))
                self._updater.bot.send_message(chat_id=self.chat_id, text=xcp_text)
        # Remove
        _log.debug('Bot: removing media %s' % file_name)
        os.remove(file_name)

    def report_motion_detected(self, detected):
        if self.chat_id:
            msg_txt = 'Something is moving...' if detected else 'Everything quiet.'
            self._updater.bot.send_message(chat_id=self.chat_id, text=msg_txt)

    def __init__(self, cam_interface, token):
        self.chat_id = None
        self._cam_interface = cam_interface
        self._updater = Updater(token=token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self._bot_start))
        self._updater.dispatcher.add_handler(CommandHandler('photo', self._bot_photo))
        self._updater.dispatcher.add_handler(CommandHandler('video', self._bot_video))
        self._updater.dispatcher.add_handler(CommandHandler('detect', self._bot_detect, pass_args=True))

        # [1] https://github.com/python-telegram-bot/python-telegram-bot/blob/5614af1/telegram/utils/request.py#L195
