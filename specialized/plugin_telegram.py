from plugins.base import PluginProcessBase, Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin, active_plugins
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import error as terr
from specialized.telegram_support.auth import AuthStatus, AuthAttemptResult
from specialized.telegram_support.auth_filter import AuthStatusFilter
import logging
from specialized.telegram_support.auth_io import save_chat_auth_storage, load_chat_auth_storage
from specialized.telegram_support.format import user_to_str
from specialized.telegram_support.handlers import make_handler as _make_handler, HandlerBase
from misc.settings import SETTINGS
from misc.logging import ensure_logging_setup, camel_to_snake
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway
from time import sleep


TELEGRAM_PLUGIN_NAME = 'TelegramRoot'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(TELEGRAM_PLUGIN_NAME))
_TELEGRAM_RETRY_CAP_SECONDS = 10


def _normalize_filters(some_telegram_plugin, filters, auth_status=None):
    if auth_status is not None:
        if filters is None:
            return some_telegram_plugin.root_telegram_plugin.auth_filters[auth_status]
        else:
            return filters & some_telegram_plugin.root_telegram_plugin.auth_filters[auth_status]
    return filters


def handle_command(command, pass_args=False, filters=None, auth_status=AuthStatus.AUTHORIZED):
    def _make_command_handler(some_telegram_plugin_, callback_, command_, pass_args_, filters_, auth_status_):
        return CommandHandler(command_, callback_,
                              filters=_normalize_filters(some_telegram_plugin_, filters_, auth_status=auth_status_),
                              pass_args=pass_args_)

    return _make_handler(_make_command_handler, command, pass_args, filters, auth_status)


def handle_message(filters=None, auth_status=AuthStatus.AUTHORIZED):
    def _make_message_handler(some_telegram_plugin_, callback_, filters_, auth_status_):
        return MessageHandler(_normalize_filters(some_telegram_plugin_, filters_, auth_status=auth_status_),
                              callback_)

    return _make_handler(_make_message_handler, filters, auth_status)


class TelegramProcessBase(PluginProcessBase, HandlerBase):
    @classmethod
    def process(cls):  # pragma: no cover
        return Process.TELEGRAM

    @property
    def root_telegram_plugin(self):
        return find_plugin(TELEGRAM_PLUGIN_NAME).telegram


@make_plugin(TELEGRAM_PLUGIN_NAME, Process.TELEGRAM)
class TelegramRootPlugin(TelegramProcessBase):
    def _save_chat_auth_storage(self):
        save_chat_auth_storage(SETTINGS.telegram.auth_file, self._auth_storage, log=_log)

    def _setup_handlers(self):
        def _collect_handlers():
            for plugin in active_plugins():
                if plugin.telegram is None or not isinstance(plugin.telegram, TelegramProcessBase):
                    continue
                yield from plugin.telegram.handlers
        if len(self._updater.dispatcher.handlers) > 0:
            return None
        cnt = 0
        for handler in _collect_handlers():
            self._updater.dispatcher.add_handler(handler)
            cnt += 1
        return cnt

    @staticmethod
    def _broadcast_media(method, chat_ids, media_obj, *args, **kwargs):
        retval = []
        file_id = None
        for chat_id in chat_ids:
            _log.info('Sending media %s to %d.', str(media_obj), chat_id)
            if file_id is None:
                _log.info('Beginning upload of media %s...', str(media_obj))
                msg = method(chat_id, media_obj, *args, **kwargs)
                if msg:
                    file_id = msg.effective_attachment.file_id
                    _log.info('Media %s uploaded as file id %s...', str(media_obj), str(file_id))
                else:
                    _log.error('Unable to send media %s.', str(media_obj))
                    return
                retval.append(msg)
            else:
                retval.append(method(chat_id, media_obj, *args, **kwargs))
        return retval

    def _send(self, method, chat_id, *args, retries=3, **kwargs):
        for i in range(retries):
            try:
                if i > 0:
                    _log.info('Retrying %d/%d...', i + 1, retries)
                return method(chat_id, *args, **kwargs)
            except terr.TimedOut as e:
                _log.error('Telegram timed out when executing %s: %s.', str(method), e.message)
            except terr.RetryAfter as e:
                _log.error('Telegram requested to retry %s in %d seconds.', str(method), e.retry_after)
                if e.retry_after > _TELEGRAM_RETRY_CAP_SECONDS:
                    _log.info('Will sleep for %d seconds only.', _TELEGRAM_RETRY_CAP_SECONDS)
                sleep(min(_TELEGRAM_RETRY_CAP_SECONDS, e.retry_after))
            except terr.InvalidToken:
                _log.error('Invalid Telegram token. Will not retry %s.', str(method))
                break
            except terr.BadRequest as e:
                _log.error('Bad request when performing %s: %s. Will not retry.', str(method), e.message)
                break
            except terr.NetworkError as e:
                _log.error('Network error when running %s: %s.', str(method), e.message)
                sleep(1)
            except terr.Unauthorized as e:
                _log.error('Not authorized to perform %s: %s. Will not retry.', str(method), e.message)
                break
            except terr.ChatMigrated as e:
                _log.warning('Chat %d moved to new chat id %d. Will update and retry.', chat_id, e.new_chat_id)
                self._auth_storage.replace_chat_id(chat_id, e.new_chat_id)
                return self._send(method, e.new_chat_id, *args, retries=retries, **kwargs)
            except terr.TelegramError as e:
                _log.error('Generic Telegram error when performing %s: %s.', str(method), e.message)
                sleep(1)
            except Exception as e:
                _log.error('Error when performing %s: %s.', str(method), str(e))
        return None

    @property
    def auth_filters(self):
        return self._auth_filters

    @pyro_expose
    @property
    def authorized_chat_ids(self):
        return list(map(lambda chat: chat.chat_id, self._auth_storage.authorized_chats))

    @pyro_expose
    @pyro_oneway
    def send_photo(self, chat_id, photo, *args, retries=3, **kwargs):
        return self._send(self._updater.bot.send_photo, chat_id, photo, *args, retries=retries, **kwargs)

    @pyro_expose
    @pyro_oneway
    def send_video(self, chat_id, video, *args, retries=3, **kwargs):
        return self._send(self._updater.bot.send_video, chat_id, video, *args, retries=retries, **kwargs)

    @pyro_expose
    @pyro_oneway
    def send_message(self, chat_id, message, *args, retries=3, **kwargs):
        return self._send(self._updater.bot.send_message, chat_id, message, *args, retries=retries, **kwargs)

    @pyro_expose
    @pyro_oneway
    def broadcast_photo(self, chat_ids, photo, *args, retries=3, **kwargs):
        return TelegramRootPlugin._broadcast_media(self.send_photo, chat_ids, photo, *args, retries=retries, **kwargs)

    @pyro_expose
    @pyro_oneway
    def broadcast_video(self, chat_ids, video, *args, retries=3, **kwargs):
        return TelegramRootPlugin._broadcast_media(self.send_video, chat_ids, video, *args, retries=retries, **kwargs)

    @pyro_expose
    @pyro_oneway
    def broadcast_message(self, chat_ids, message, *args, retries=3, **kwargs):
        return list([self.send_message(chat_id, message, *args, retries=retries, **kwargs) for chat_id in chat_ids])

    @pyro_expose
    @pyro_oneway
    def reply_message(self, update, message, *args, retries=3, **kwargs):
        return self.send_message(update.message.chat_id, message, *args,
                                 retries=retries, reply_to_message_id=update.message.message_id, **kwargs)

    @pyro_expose
    @pyro_oneway
    def reply_photo(self, update, photo, *args, retries=3, **kwargs):
        return self.send_photo(update.message.chat_id, photo, *args,
                               retries=retries, reply_to_message_id=update.message.message_id, **kwargs)

    @pyro_expose
    @pyro_oneway
    def reply_video(self, update, video, *args, retries=3, **kwargs):
        return self.send_video(update.message.chat_id, video, *args,
                               retries=retries, reply_to_message_id=update.message.message_id, **kwargs)

    def __init__(self):
        super(TelegramRootPlugin, self).__init__()
        self._updater = Updater(token=SETTINGS.telegram.token)
        self._auth_storage = load_chat_auth_storage(SETTINGS.telegram.auth_file, log=_log)
        self._auth_filters = dict({
            status: AuthStatusFilter(self._auth_storage, status) for status in AuthStatus
        })

    def __enter__(self):
        super(TelegramRootPlugin, self).__enter__()
        _log.info('Setting up Telegram handlers...')
        cnt_handlers = self._setup_handlers()
        if cnt_handlers is None:
            _log.info('Handlers already registered. Beginning serving...')
        else:
            _log.info('Registered %d handler(s). Beginning serving...', cnt_handlers)
        self._updater.start_polling(poll_interval=1, timeout=20, clean=True)
        _log.info('Telegram bot is being served.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(TelegramRootPlugin, self).__exit__(exc_type, exc_val, exc_tb)
        _log.info('Stopping serving Telegram bot...')
        self._updater.stop()
        _log.info('Telegram bot was stopped.')

    @handle_command('start', auth_status=AuthStatus.UNKNOWN)
    def _bot_start_new_chat(self, bot, upd):
        user = user_to_str(upd.message.from_user)
        _log.info('Access requested by %s', user)
        password = self._auth_storage[upd.message.chat_id].start_auth(user)
        self._save_chat_auth_storage()
        print('\n\nChat ID: %d, User: %s, Password: %s\n\n' % (upd.message.chat_id, user, password))
        bot.send_message(chat_id=upd.message.chat_id, text='Reply with the pass that you can read on the console.')

    @handle_command('start', auth_status=AuthStatus.ONGOING)
    def _bot_start_resume_auth(self, bot, upd):
        _log.info('Authentication resumed for chat %d, user %s.', upd.message.chat_id,
                  user_to_str(upd.message.from_user))
        bot.send_message(chat_id=upd.message.chat_id, text='Reply with the pass that you can read on the console.')

    @handle_command('start', auth_status=AuthStatus.AUTHORIZED)
    def _bot_start(self, bot, upd):
        _log.info('Started on chat %d', upd.message.chat_id)
        bot.send_message(chat_id=upd.message.chat_id, text='Ratcam is active.')

    @handle_message(Filters.text, auth_status=AuthStatus.ONGOING)
    def _bot_try_auth(self, bot, upd):
        password = upd.message.text
        result = self._auth_storage[upd.message.chat_id].try_auth(password)
        self._save_chat_auth_storage()
        if result == AuthAttemptResult.AUTHENTICATED:
            bot.send_message(chat_id=upd.message.chat_id, text='Authenticated.')
        elif result == AuthAttemptResult.WRONG_TOKEN:
            bot.send_message(chat_id=upd.message.chat_id, text='Incorrect password.')
        elif result == AuthAttemptResult.EXPIRED:
            bot.send_message(chat_id=upd.message.chat_id, text='Your password expired.')
        elif result == AuthAttemptResult.TOO_MANY_RETRIES:
            bot.send_message(chat_id=upd.message.chat_id, text='Number of attempts exceeded.')
        _log.info('Authentication attempt for chat %d, user %s, outcome: %s', upd.message.chat_id,
                  user_to_str(upd.message.from_user), result)

    @handle_message(Filters.status_update.left_chat_member, auth_status=None)
    def _bot_user_left(self, _, upd):
        if upd.message.chat.get_members_count() <= 1:
            _log.info('Exiting chat %d (%s).', upd.message.chat_id, str(upd.message.chat.title))
            self._auth_storage[upd.message.chat_id].revoke_auth()
            self._save_chat_auth_storage()
