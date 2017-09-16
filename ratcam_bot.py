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

from cam_manager import CameraManager, EventType
from misc import log
from telegram.ext import Updater, CommandHandler
import io
import os

class RatcamBot(CameraManager):

    def _bot_start(self, bot, update):
        if self.chat_id != None:
            return
        log().info('Ratcam bot started by user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        self.chat_id = update.message.chat_id
        if self.bot:
            self.bot.send_message(chat_id=self.chat_id, text='Ratcam SimpleBot active.')

    def _bot_photo(self, bot, update):
        if update.message.chat_id != self.chat_id:
            return
        log().info('A picture is going to be taken for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        self._cam_mgr.take_photo()

    def _bot_video(self, bot, update):
        if update.message.chat_id != self.chat_id:
            return
        log().info('A video is going to be recorder for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        self._cam_mgr.take_video()

    @property
    def bot(self):
        return self._updater.bot if self.chat_id is not None else None

    def __enter__(self):
        super(RatcamBot, self).__enter__()
        self._updater.start_polling(clean=True)
        log().info('Starting up camera and polling.')


    def __exit__(self, exc_type, exc_val, exc_tb):
        log().info('Stopping camera and polling.')
        super(RatcamBot, self).__exit__(exc_type, exc_val, exc_tb)

    def _report_event(self, event_type, file_name = None):
        if event_type == EventType.MOTION_DETECTED:
            if self.bot:
                self.bot.send_message(chat_id=self.chat_id, text='Something is moving...')
        elif event_type == EventType.MOTION_STILL:
            if self.bot:
                self.bot.send_message(chat_id=self.chat_id, text='Everything quiet.')
        elif event_type == EventType.PHOTO_READY:
            if self.bot:
                self.bot.send_photo(chat_id=self.chat_id, photo=file_name)
            os.remove(file_name)
        elif event_type == EventType.VIDEO_READY:
            if self.bot:
                self.bot.send_video(chat_id=self.chat_id, video=file_name)
            os.remove(file_name)

    def __init__(self, token):
        super(RatcamBot, self).__init__()
        self.chat_id = None
        self._updater = Updater(token=token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self._bot_start))
        self._updater.dispatcher.add_handler(CommandHandler('photo', self._bot_photo))
        self._updater.dispatcher.add_handler(CommandHandler('video', self._bot_video))
