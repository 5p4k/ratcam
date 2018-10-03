from plugins.base import PluginProcessBase, Process
from plugins.decorators import make_plugin
from plugins.processes_host import find_plugin, active_plugins
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from specialized.telegram_support.auth import AuthStatus, AuthAttemptResult
from specialized.telegram_support.auth_filter import AuthStatusFilter
import logging
from specialized.telegram_support.auth_io import save_chat_auth_storage, load_chat_auth_storage
from specialized.telegram_support.format import user_to_str
from specialized.telegram_support.handlers import make_handler as _make_handler, HandlerBase
from misc.settings import SETTINGS
from misc.logging import ensure_logging_setup, camel_to_snake
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway


TELEGRAM_PLUGIN_NAME = 'RatcamBot'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(TELEGRAM_PLUGIN_NAME))


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
    @property
    def root_telegram_plugin(self):
        return find_plugin(TELEGRAM_PLUGIN_NAME).telegram


@make_plugin(TELEGRAM_PLUGIN_NAME, Process.TELEGRAM)
class TelegramProcess(TelegramProcessBase):
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

    def _broadcast(self, method, *args, **kwargs):
        for chat in self._auth_storage.authorized_chats:
            method(chat.chat_id, *args, **kwargs)

    @property
    def auth_filters(self):
        return self._auth_filters

    @pyro_expose
    @property
    def authorized_chat_ids(self):
        return list(map(lambda chat: chat.chat_id, self._auth_storage.authorized_chats))

    @pyro_expose
    @pyro_oneway
    def send_photo(self, *args, **kwargs):
        self._updater.bot.send_photo(*args, **kwargs)

    @pyro_expose
    @pyro_oneway
    def send_message(self, *args, **kwargs):
        self._updater.bot.send_message(*args, **kwargs)

    @pyro_expose
    @pyro_oneway
    def broadcast_photo(self, *args, **kwargs):
        self._broadcast(self._updater.bot.send_photo, *args, **kwargs)

    @pyro_expose
    @pyro_oneway
    def broadcast_message(self, *args, **kwargs):
        self._broadcast(self._updater.bot.send_message, *args, **kwargs)

    def __init__(self):
        super(TelegramProcess, self).__init__()
        self._updater = Updater(token=SETTINGS.telegram.token)
        self._auth_storage = load_chat_auth_storage(SETTINGS.telegram.auth_file, log=_log)
        self._auth_filters = dict({
            status: AuthStatusFilter(self._auth_storage, status) for status in AuthStatus
        })

    def __enter__(self):
        super(TelegramProcess, self).__enter__()
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
        super(TelegramProcess, self).__exit__(exc_type, exc_val, exc_tb)
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
