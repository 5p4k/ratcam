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
from datetime import time, datetime

_log = logging.getLogger('ratcam')

YES = ['y', 'yes', '1', 'on', 't', 'true']
NO = ['n', 'no', '0', 'off', 'f', 'false']

BOT_PHOTO_TIMEOUT = 20
BOT_VIDEO_TIMEOUT = 60

AUTH_FILE = 'auth.json'


def highest_resolution_photo(photo_sizes):
    return max(photo_sizes, key=lambda photo_size: photo_size.width * photo_size.height)


def usr_to_str(usr):
    return '%s, %s (%s)' % (usr.first_name, usr.last_name, usr.username)


def human_file_size(file_name, suffix='B'):
    sz = os.path.getsize(file_name)
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(sz) < 1000.0:
            return "%3.1f%s%s" % (sz, unit, suffix)
        sz /= 1000.0
    return "%.1f%s%s" % (sz, 'Y', suffix)


def parse_time(txt):
    pieces = txt.split(':')
    if len(pieces) in [2, 3]:
        try:
            h = int(pieces[0])
            m = int(pieces[1])
            s = 0
            if len(pieces) == 3:
                s = int(pieces[2])
            return time(hour=h, minute=m, second=s)
        finally:
            pass
    return None


class BotManager:
    @property
    def detection_desc(self):
        retval = 'Detection is '
        retval += 'ON.' if self.detection_enabled else 'OFF.'
        if self._detection_on_time is not None and self._detection_off_time is not None:
            retval += ' Detection was scheduled between %s and %s.' %\
                      (self._detection_on_time.isoformat(), self._detection_off_time.isoformat())
        elif self._detection_on_time is not None:
            retval += ' Detection was scheduled to be turned ON at ' % self._detection_on_time.isoformat()
        elif self._detection_off_time is not None:
            retval += ' Detection was scheduled to be turned OFF at ' % self._detection_off_time.isoformat()
        return retval

    def _bot_start(self, bot, upd):
        bot.send_message(chat_id=upd.message.chat_id, text='Ratcam is active. %s' % self.detection_desc)

    def _bot_start_new_chat(self, bot, upd):
        _log.info('Bot: %s requested access', usr_to_str(upd.message.from_user))
        usr_str = usr_to_str(upd.message.from_user)
        pwd = self._auth.start_auth(upd.message.chat_id, usr_str)
        print('\n\nChat ID: %d, User: %s, Password: %s\n\n' % (upd.message.chat_id, usr_str, pwd))
        bot.send_message(chat_id=upd.message.chat_id, text='Reply with the pass that you can read on the console.')

    def _bot_start_auth(self, bot, upd):
        _log.info('Bot: authentication resumed for chat %d, user %s.', upd.message.chat_id,
                  usr_to_str(upd.message.from_user))
        bot.send_message(chat_id=upd.message.chat_id, text='Reply with the pass that you can read on the console.')

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
            txt = self.detection_desc
            bot.send_message(chat_id=upd.message.chat_id, reply_to_message_id=upd.message.message_id, text=txt)
            return
        # Check if it's a valid command
        if len(args) in [1, 2, 3]:
            switch = args[0].strip().lower()
            if switch in YES or switch in NO:
                on_off = switch in YES
                desc = 'ON' if on_off else 'OFF'
                if len(args) == 1:
                    # Actually toggle detection
                    self.detection_enabled = on_off
                    self._broadcast(text='User %s turned %s detection.' % (usr_to_str(upd.message.from_user), desc))
                    _log.info('Bot: %s turned %s detection.', usr_to_str(upd.message.from_user), desc)
                    return
                elif len(args) == 2 and args[1].strip().lower() == 'never':
                    if on_off:
                        self._detection_on_time = None
                        desc = 'User %s deleted detection %s schedule.' % (usr_to_str(upd.message.from_user), desc)
                        self._broadcast(text=desc)
                        _log.info('Bot: %s' % desc)
                    else:
                        self._detection_on_time = None
                        desc = 'User %s deleted detection %s schedule.' % (usr_to_str(upd.message.from_user), desc)
                        self._broadcast(text=desc)
                        _log.info('Bot: %s' % desc)
                    return
                elif len(args) == 3 and args[1].strip().lower() == 'at':
                    toggle_time = parse_time(args[2].strip())
                    if toggle_time:
                        if on_off:
                            self._detection_on_time = toggle_time
                            desc = 'User %s scheduled to turn detection %s at %s.' % \
                                   (usr_to_str(upd.message.from_user), desc, toggle_time.isoformat())
                            self._broadcast(text=desc)
                            _log.info('Bot: %s' % desc)
                        else:
                            self._detection_on_time = toggle_time
                            desc = 'User %s scheduled to turn detection %s at %s.' % \
                                   (usr_to_str(upd.message.from_user), desc, toggle_time.isoformat())
                            self._broadcast(text=desc)
                            _log.info('Bot: %s' % desc)
                        return
        bot.send_message(chat_id=upd.message.chat_id, reply_to_message_id=upd.message.message_id,
                         text='I did not understand.')

    def _bot_photo(self, _, upd):
        _log.info('Bot: taking photo for %s.', usr_to_str(upd.message.from_user))
        self._cam_interface.request_photo()

    def _bot_video(self, _, upd):
        _log.info('Bot: taking video for %s.', usr_to_str(upd.message.from_user))
        self._cam_interface.request_video()

    def _bot_logout(self, _, upd):
        _log.info('Bot: requested logout from chat %d (%s).', upd.message.chat_id, str(upd.message.chat.title))
        self._auth.revoke_auth(upd.message.chat_id)

    def _bot_user_left(self, _, upd):
        if upd.message.chat.get_members_count() <= 1:
            _log.info('Bot: exiting chat %d (%s).', upd.message.chat_id, str(upd.message.chat.title))
            self._auth.revoke_auth(upd.message.chat_id)

    @property
    def detection_enabled(self):
        return self._detection_enabled_cached

    @detection_enabled.setter
    def detection_enabled(self, value):
        if self._detection_enabled_cached == value:
            return
        self._detection_enabled_cached = value
        self._cam_interface.toggle_detection(value)

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

    def _upload_and_return_media_id(self, chat_id, file_name, media_type):
        file_size = human_file_size(file_name)
        try:
            # Send the media and extract the video
            _log.info('Bot: sending media %s (%s)', file_name, file_size)
            with open(file_name, 'rb') as file:
                if media_type == 'mp4':
                    msg = self._updater.bot.send_video(chat_id=chat_id, video=file, timeout=BOT_VIDEO_TIMEOUT)
                    # Videos with no audio are sent as gifs (doesn't matter using effective_attachment)
                    return msg.effective_attachment.file_id
                elif media_type == 'jpeg':
                    msg = self._updater.bot.send_photo(chat_id=chat_id, photo=file, timeout=BOT_PHOTO_TIMEOUT)
                    # Send highest resolution media
                    return highest_resolution_photo(msg.photo).file_id
        except Exception as e:
            _log.error('Unable to send video, error: %s', str(e))
            # Can't do any better logging,  because everything is hidden behind Telegram exceptions [1]
            xcp_text = 'Could not send %s (%s); exception: "%s".' % (media_type, file_size, str(e))
            self._broadcast(text=xcp_text)
        return None

    def send_media(self, file_name, media_type):
        file_id = None
        for chat_id in self._auth.authorized_chat_ids:
            if file_id is None:
                file_id = self._upload_and_return_media_id(chat_id, file_name, media_type)
                if not file_id:
                    break
            else:
                if media_type == 'mp4':
                    # NOTE Videos with no audio are sent as gif, so when sending them again we should just send them
                    # along as document
                    # self._updater.bot.send_video(chat_id=chat_id, video=file_id, timeout=BOT_VIDEO_TIMEOUT)
                    self._updater.bot.send_document(chat_id=chat_id, document=file_id, timeout=BOT_VIDEO_TIMEOUT)
                elif media_type == 'jpeg':
                    self._updater.bot.send_photo(chat_id, photo=file_id, timeout=BOT_PHOTO_TIMEOUT)
        _log.debug('Bot: removing media %s', file_name)
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
                json.dump(self._auth, stream, cls=ChatAuthJSONCodec, sort_keys=True, indent=4)
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
        disp.add_handler(CommandHandler('logout', self._bot_logout, filters=filters[AuthStatus.OK]))

        # Detect when users leave and close the chat.
        disp.add_handler(MessageHandler(Filters.status_update.left_chat_member, self._bot_user_left))

    def spin(self):
        if datetime.now().time() > self._detection_on_time:
            self.detection_enabled = True
            self._broadcast(text='Turning on detection (scheduled).')
        elif datetime.now().time() > self._detection_off_time:
            self.detection_enabled = False
            self._broadcast(text='Turning off detection (scheduled).')

    def __init__(self, cam_interface, token):
        self._cam_interface = cam_interface
        self._detection_on_time = None
        self._detection_off_time = None
        self._detection_enabled_cached = False
        self._updater = Updater(token=token)
        self._auth = ChatAuth()
        # Try to load a pre-existent authorization
        self._try_load_auth()
        self._setup_handlers()
        for chat_id in list(self._auth.authorized_chat_ids):
            chat = self._updater.bot.get_chat(chat_id)
            if chat.get_members_count() <= 1:
                print('Exiting chat %d %s' % (chat_id, str(chat.title)))
                self._auth.revoke_auth(chat_id)

        # [1] https://github.com/python-telegram-bot/python-telegram-bot/blob/5614af1/telegram/utils/request.py#L195
