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

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import os
import logging
from auth import ChatAuth, ChatAuthJSONCodec, AuthStatusFilter, AuthStatus, AuthAttemptResult
import json

_log = logging.getLogger('ratcam')

YES = ['y', 'yes', '1', 'on', 't', 'true']
NO = ['n', 'no', '0', 'off', 'f', 'false']

BOT_PHOTO_TIMEOUT = 20
BOT_VIDEO_TIMEOUT = 60

AUTH_FILE = 'auth.json'


def usr_to_str(usr):
    return '%s, %s (%s)' % (usr.first_name, usr.last_name, usr.username)


def human_file_size(file_name, suffix='B'):
    sz = os.path.getsize(file_name)
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(sz) < 1000.0:
            return "%3.1f%s%s" % (sz, unit, suffix)
        sz /= 1000.0
    return "%.1f%s%s" % (sz, 'Y', suffix)


class BotManager:
    @property
    def _detection_str(self):
        return 'ON' if self._detection_enabled_cached else 'OFF'

    def _bot_start(self, bot, upd):
        bot.send_message(chat_id=upd.message.chat_id, text='Ratcam is active. Detection is %s.' % self._detection_str)

    def _bot_start_new_chat(self, bot, upd):
        _log.info('Bot: %s requested access', usr_to_str(upd.message.from_user))
        usr_str = usr_to_str(upd.message.from_user)
        pwd = self._auth.start_auth(upd.message.chat_id, usr_str)
        print('\n\nChat ID: %d, User: %s, Password: %s\n\n' % (upd.message.chat_id, usr_str, pwd))
        bot.send_message(chat_id=upd.message.chat_id, text='Insert the pass that you can read on the Pi\'s console.')

    @staticmethod  # Silent PyCharm warning
    def _bot_start_auth(self, bot, upd):
        _log.info('Bot: authentication resumed for chat %d, user %s.', upd.message.chat_id,
                  usr_to_str(upd.message.from_user))
        bot.send_message(chat_id=upd.message.chat_id, text='Insert the pass that you can read on the Pi\'s console.')

    def _bot_try_auth(self, bot, upd):
        pwd = upd.message.text
        result = self._auth.do_auth(upd.message.chat_id, pwd)
        if result == AuthAttemptResult.AUTHENTICATED:
            bot.send_message(chat_id=upd.message.chat_id, text='Authenticated.')
        elif result == AuthAttemptResult.WRONG_PASSWORD:
            bot.send_message(chat_id=upd.message.chat_id, text='Incorrect password.')
        elif result == AuthAttemptResult.EXPIRED:
            bot.send_message(chat_id=upd.message.chat_id, text='Your password expired.')
        elif result == AuthAttemptResult.TOO_MANY_RETRIES:
            bot.send_message(chat_id=upd.message.chat_id, text='Number of attempts exceeded.')
        _log.info('Bot: authentication attempt for chat %d, user %s, outcome: %s', upd.message.chat_id,
                  usr_to_str(upd.message.from_user), result)

    def _bot_detect(self, bot, upd, args):
        if len(args) == 0:
            txt = 'Detection is currently %s. Type /detect on or /detect off to change it.' % self._detection_str
            bot.send_message(chat_id=upd.message.chat_id, reply_to_message_id=upd.message.message_id, text=txt)
            return
        # Check if it's a valid command
        switch = args[0].strip().lower()
        if switch not in YES and switch not in NO:
            bot.send_message(chat_id=upd.message.chat_id, reply_to_message_id=upd.message.message_id,
                             text='I did not understand.')
            return
        # Actually toggle detection
        if switch in YES:
            self._detection_enabled_cached = True
            self._cam_interface.toggle_detection(True)
        elif switch in NO:
            self._detection_enabled_cached = False
            self._cam_interface.toggle_detection(False)
        _log.info('Bot: %s turned %s detection.', usr_to_str(upd.message.from_user), self._detection_str)

    def _bot_photo(self, _, upd):
        _log.info('Bot: taking photo for %s.', usr_to_str(upd.message.from_user))
        self._cam_interface.request_photo()

    def _bot_video(self, _, upd):
        _log.info('Bot: taking video for %s.', usr_to_str(upd.message.from_user))
        self._cam_interface.request_video()

    def __enter__(self):
        self._updater.start_polling(clean=True)
        _log.info('Bot: enter.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._updater.stop()
        self._dump_auth()
        _log.info('Bot: exit.')

    def _broadcast(self, *args, **kwargs):
        for chat_id in self._auth.authorized_chat_ids:
            self._updater.bot.send_message(chat_id=chat_id, *args, **kwargs)

    def _upload_and_return_media(self, chat_id, file_name, media_type):
        file_size = human_file_size(file_name)
        try:
            # Send the media and extract the video
            _log.info('Bot: sending media %s (%s)' % (file_name, file_size))
            with open(file_name, 'rb') as file:
                if media_type == 'mp4':
                    return self._updater.bot.send_video(chat_id=chat_id, video=file, timeout=BOT_VIDEO_TIMEOUT).video
                elif media_type == 'jpeg':
                    return self._updater.bot.send_photo(chat_id=chat_id, photo=file, timeout=BOT_PHOTO_TIMEOUT).photo
        except Exception as e:
            _log.error('Unable to send video, error: %s', str(e))
            # Can't do any better logging,  because everything is hidden behind Telegram exceptions [1]
            xcp_text = 'Could not send %s (%s); exception: "%s".' % (media_type, file_size, str(e))
            self._broadcast(text=xcp_text)
        return None

    def send_media(self, file_name, media_type):
        telegram_media = None
        for chat_id in self._auth.authorized_chat_ids:
            if telegram_media is None:
                telegram_media = self._upload_and_return_media(chat_id, file_name, media_type)
                if not telegram_media:
                    break
            else:
                if media_type == 'mp4':
                    self._updater.bot.send_video(chat_id, video=telegram_media, timeout=BOT_VIDEO_TIMEOUT)
                elif media_type == 'jpeg':
                    self._updater.bot.send_photo(chat_id, video=telegram_media, timeout=BOT_PHOTO_TIMEOUT)
        _log.debug('Bot: removing media %s' % file_name)
        os.remove(file_name)

    def report_motion_detected(self, detected):
        self._broadcast(text=('Something is moving...' if detected else 'Everything quiet.'))

    def _try_load_auth(self):
        if os.path.isfile(AUTH_FILE):
            new_auth = None
            try:
                with open(AUTH_FILE, 'r') as stream:
                    new_auth = json.load(stream, object_hook=ChatAuthJSONCodec.hook)
            except Exception as e:
                _log.warning('Unable to load auth file %s. Error: %s', AUTH_FILE, str(e))
            if new_auth:
                self._auth = new_auth

    def _dump_auth(self):
        try:
            with open(AUTH_FILE, 'w') as stream:
                json.dump(self._auth, stream, cls=ChatAuthJSONCodec)
        except Exception as e:
            _log.warning('Unable to save auth file %s. Error: %s', AUTH_FILE, str(e))

    def _setup_handlers(self):
        # Alias for the dispatcher
        disp = self._updater.dispatcher
        # Construct one filter per type for quick referral
        filters = {status: AuthStatusFilter(self._auth, status) for status in AuthStatus}

        # Handle start command in a different way depending on the authentication status
        disp.add_handler(CommandHandler('start', self._bot_start_new_chat, filters=filters[AuthStatus.UNKNOWN]))
        disp.add_handler(CommandHandler('start', self._bot_start_auth, filters=filters[AuthStatus.ONGOING]))
        disp.add_handler(CommandHandler('start', self._bot_start, filters=filters[AuthStatus.OK]))

        # This is the actual login command
        disp.add_handler(MessageHandler(Filters.text & filters[AuthStatus.ONGOING], self._bot_try_auth))

        # Commands available only when you're logged in
        disp.add_handler(CommandHandler('photo', self._bot_photo, filters=filters[AuthStatus.OK]))
        disp.add_handler(CommandHandler('video', self._bot_video, filters=filters[AuthStatus.OK]))
        disp.add_handler(CommandHandler('detect', self._bot_detect, pass_args=True, filters=filters[AuthStatus.OK]))

    def __init__(self, cam_interface, token):
        self._cam_interface = cam_interface
        self._detection_enabled_cached = False
        self._updater = Updater(token=token)
        self._auth = ChatAuth()
        # Try to load a pre-existent authorization
        self._try_load_auth()
        self._setup_handlers()

        # [1] https://github.com/python-telegram-bot/python-telegram-bot/blob/5614af1/telegram/utils/request.py#L195
