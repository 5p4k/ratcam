from ..plugins import PluginProcessBase, make_plugin, Process
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from .telegram_support.auth import AuthStatus, AuthAttemptResult
from ..misc.extended_json_codec import ExtendedJSONCodec
from .telegram_support.auth_filter import AuthStatusFilter
from Pyro4 import expose as pyro_expose
import logging
from .telegram_support.auth_io import save_chat_auth_storage, load_chat_auth_storage
from .telegram_support.inspect import get_cls_of_method, bind_method
from .telegram_support.format import user_to_str


_TELEGRAM_PLUGIN_NAME = 'RatcamBot'
_TELEGRAM_TEMP_TOKEN = 'Replace me with a token value fetched from shared settings'
_TELEGRAM_TEMP_AUTH_FILE = 'telegram_auth.json'

_log = logging.getLogger(_TELEGRAM_PLUGIN_NAME.lower())


class TelegramProcessBase(PluginProcessBase):
    _HANDLER_CREATOR_FN = []

    @property
    def handlers(self):
        return [create_handler_fn(self) for create_handler_fn in self.__class__._HANDLER_CREATOR_FN]

    @property
    def telegram_plugin(self):
        return self.plugins[_TELEGRAM_PLUGIN_NAME]


class _HandleCommand:
    def __call__(self, f):
        cls = get_cls_of_method(f)
        if not issubclass(cls, TelegramProcessBase):
            raise ValueError('A class need to be subclass of TelegramProcessBase to support this decorator.')

        def _create_handler(plugin_self):
            filters = self._filters
            if self._auth_status is not None:
                filters.append(plugin_self.telegram_plugin.auth_filters[self._auth_status])
            callback = bind_method(plugin_self, f)
            return CommandHandler(self._command, callback, pass_args=self._pass_args, filters=filters)

        cls._HANDLER_CREATOR_FN.append(_create_handler)
        return f

    def __init__(self, command, pass_args=False, auth_status=AuthStatus.AUTHORIZED, filters=None):
        self._command = command
        self._pass_args = pass_args
        self._auth_status = auth_status
        self._filters = [] if filters is None else list(filters)


class _HandleMessage:
    def __call__(self, f):
        cls = get_cls_of_method(f)
        if not issubclass(cls, TelegramProcessBase):
            raise ValueError('A class need to be subclass of TelegramProcessBase to support this decorator.')

        def _create_handler(plugin_self):
            filters = self._filters
            if self._auth_status is not None:
                filters.append(plugin_self.telegram_plugin.auth_filters[self._auth_status])
            callback = bind_method(plugin_self, f)
            return MessageHandler(filters, callback)

        cls._HANDLER_CREATOR_FN.append(_create_handler)
        return f

    def __init__(self, filters, auth_status=AuthStatus.AUTHORIZED):
        self._filters = list(filters)
        self._auth_status = auth_status


handle_command = _HandleCommand
handle_message = _HandleMessage


@make_plugin(_TELEGRAM_PLUGIN_NAME, Process.TELEGRAM)
class TelegramProcess(TelegramProcessBase):
    def _save_chat_auth_storage(self):
        save_chat_auth_storage(_TELEGRAM_TEMP_AUTH_FILE, self._auth_storage, log=_log)

    def _collect_handlers(self):
        for plugin_name, plugin in self.plugins.items():
            plugin_telegram_process = plugin[Process.TELEGRAM]
            if plugin_telegram_process is None or not hasattr(plugin_telegram_process, 'handlers'):
                continue
            yield from plugin_telegram_process.handlers

    def _setup_handlers(self):
        if len(self._updater.dispatcher.handlers) > 0:
            return None
        cnt = 0
        for handler in self._collect_handlers():
            self._updater.dispatcher.add_handler(handler)
            cnt += 1
        return cnt

    @property
    def auth_filters(self):
        return self._auth_filters

    def __init__(self):
        super(TelegramProcess, self).__init__()
        self._updater = Updater(token=_TELEGRAM_TEMP_TOKEN)
        self._auth_storage = load_chat_auth_storage(_TELEGRAM_TEMP_AUTH_FILE, log=_log)
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

    @handle_command('start', auth_status=AuthStatus.OK)
    def _bot_start(self, bot, upd):
        _log.info('Started on chat %d', upd.message.chat_id)
        bot.send_message(chat_id=upd.message.chat_id, text='Ratcam is active.')

    @handle_message([Filters.text], auth_status=AuthStatus.ONGOING)
    def _bot_try_auth(self, bot, upd):
        password = upd.message.text
        result = self._auth_storage[upd.message.chat_id].try_auth(password)
        self._save_chat_auth_storage()
        if result == AuthAttemptResult.AUTHENTICATED:
            bot.send_message(chat_id=upd.message.chat_id, text='Authenticated.')
        elif result == AuthAttemptResult.WRONG_PASSWORD:
            bot.send_message(chat_id=upd.message.chat_id, text='Incorrect password.')
        elif result == AuthAttemptResult.EXPIRED:
            bot.send_message(chat_id=upd.message.chat_id, text='Your password expired.')
        elif result == AuthAttemptResult.TOO_MANY_RETRIES:
            bot.send_message(chat_id=upd.message.chat_id, text='Number of attempts exceeded.')
        _log.info('Authentication attempt for chat %d, user %s, outcome: %s', upd.message.chat_id,
                  user_to_str(upd.message.from_user), result)

    @handle_message([Filters.status_update.left_chat_member], auth_status=None)
    def _bot_user_left(self, _, upd):
        if upd.message.chat.get_members_count() <= 1:
            _log.info('Exiting chat %d (%s).', upd.message.chat_id, str(upd.message.chat.title))
            self._auth_storage[upd.message.chat_id].revoke_auth()
            self._save_chat_auth_storage()
