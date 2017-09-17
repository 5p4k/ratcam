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

from misc import log
from telegram.ext import Updater, CommandHandler
import io
import os

class RatcamBot: # TODO Bot process?

    def _bot_start(self, bot, update):
        if self.chat_id != None:
            return
        log().info('Ratcam bot started by user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        self.chat_id = update.message.chat_id
        if self.chat_id:
            bot.send_message(chat_id=self.chat_id, text='Ratcam SimpleBot active.')

    def _bot_photo(self, bot, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        log().info('A picture is going to be taken for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        # Signal
        self.state.photo_request = True

    def _bot_video(self, bot, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        log().info('A video is going to be recorder for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        # Signal
        self.state.video_request = True

    def __enter__(self):
        super(RatcamBot, self).__enter__()
        self._updater.start_polling(clean=True)
        log().info('Starting up camera and polling.')


    def __exit__(self, exc_type, exc_val, exc_tb):
        log().info('Stopping camera and polling.')

    def spin(self):
        if self.state.motion_began and self.chat_id:
            self._updater.bot.send_message(chat_id=self.chat_id, text='Something is moving...')
        if self.state.motion_stopped and self.chat_id:
            self._updater.bot.send_message(chat_id=self.chat_id, text='Everything quiet.')
        # Pop one media
        file_name, media_type = self.state.pop_media()
        if file_name:
            if media_type == 'video':
                self._updater.bot.send_video(chat_id=self.chat_id, video=file_name)
            elif media_type == 'photo':
                self._updater.bot.send_photo(chat_id=self.chat_id, photo=file_name)
            # Remove
            os.remove(file_name)


    def __init__(self, state, token):
        self.chat_id = None
        self.state = state
        self._updater = Updater(token=token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self._bot_start))
        self._updater.dispatcher.add_handler(CommandHandler('photo', self._bot_photo))
        self._updater.dispatcher.add_handler(CommandHandler('video', self._bot_video))
