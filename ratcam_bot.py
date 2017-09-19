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
import io
import os
import logging

_log = logging.getLogger('ratcam')

def human_file_size(file_name, suffix='B'):
    sz = os.path.getsize(file_name)
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(sz) < 1000.0:
            return "%3.1f%s%s" % (sz, unit, suffix)
        sz /= 1000.0
    return "%.1f%s%s" % (sz, 'Y', suffix)


class BotProcess:

    def _bot_start(self, bot, update):
        if self.chat_id != None:
            return
        _log.info('BotProcess: started by user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        self.chat_id = update.message.chat_id
        if self.chat_id:
            bot.send_message(chat_id=self.chat_id, text='Ratcam SimpleBot active.')

    def _bot_photo(self, bot, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        _log.info('BotProcess: taking photo for %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        # Signal
        self.state.photo_request = True

    def _bot_video(self, bot, update):
        if update.message.chat_id != self.chat_id or not self.chat_id:
            return
        _log.info('BotProcess: taking video for %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        # Signal
        self.state.video_request = True

    def __enter__(self):
        self._updater.start_polling(clean=True)
        _log.info('BotProcess: enter.')


    def __exit__(self, exc_type, exc_val, exc_tb):
        _log.info('BotProcess: exit.')

    def spin(self):
        if self.state.motion_began and self.chat_id:
            self._updater.bot.send_message(chat_id=self.chat_id, text='Something is moving...')
        if self.state.motion_stopped and self.chat_id:
            self._updater.bot.send_message(chat_id=self.chat_id, text='Everything quiet.')
        # Pop one media
        file_name, media_type = self.state.pop_media()
        if file_name:
            if self.chat_id:
                try:
                    _log.info('BotProcess: sending media %s (%s)' % (file_name, human_file_size(file_name)))
                    if media_type == 'video':
                        with open(file_name, 'rb') as file:
                            self._updater.bot.send_video(chat_id=self.chat_id, video=file, timeout=60)
                    elif media_type == 'photo':
                        with open(file_name, 'rb') as file:
                            self._updater.bot.send_photo(chat_id=self.chat_id, photo=file, timeout=20)
                except Exception as e:
                    _log.error(str(e))
                    # Can't do any better logging,  because everything is hidden behind Telegram
                    # exceptions [1]
                    self._updater.bot.send_message(chat_id=self.chat_id,
                        text='Could not send %s (%s); exception: "%s".' % (media_type, human_file_size(file_name), str(e)))
                finally:
                    # Remove
                    _log.debug('BotProcess: removing media %s' % file_name)
                    os.remove(file_name)


    def __init__(self, state, token):
        self.chat_id = None
        self.state = state
        self._updater = Updater(token=token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self._bot_start))
        self._updater.dispatcher.add_handler(CommandHandler('photo', self._bot_photo))
        self._updater.dispatcher.add_handler(CommandHandler('video', self._bot_video))


# [1] https://github.com/python-telegram-bot/python-telegram-bot/blob/5614af18474b1ec975192aea6ce440231866be60/telegram/utils/request.py#L195