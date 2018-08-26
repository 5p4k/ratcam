import os
import json
from specialized.telegram_support.auth import ChatAuthStorage
from misc.extended_json_codec import ExtendedJSONCodec


def load_chat_auth_storage(path, log=None):
    def _discard_data():
        if log:
            log.error('Data will be discarded.')
        # noinspection PyBroadException
        try:
            os.rename(path, path + '.malformed')
        except:
            pass

    path = os.path.abspath(path)
    if os.path.isfile(path):
        try:
            with open(path, 'r') as fp:
                json_data = json.load(fp, object_hook=ExtendedJSONCodec.hook)
            if json_data is None or not isinstance(json_data, ChatAuthStorage):
                if log:
                    log.error('JSON auth file %s does not contain valid authorization data.', path)
                _discard_data()
            else:
                return json_data
        except OSError as exc:
            if log:
                log.warning('Could not load auth file %s, error: %s', path, exc.strerror)
        except json.JSONDecodeError as exc:
            if log:
                log.error('Malformed JSON auth file %s:%d:d, error: %s', path, exc.lineno, exc.colno, exc.msg)
            _discard_data()

    return ChatAuthStorage()


def save_chat_auth_storage(path, chat_auth_storage, log=None):
    path = os.path.abspath(path)
    try:
        with open(path, 'w') as fp:
            json.dump(chat_auth_storage, fp, cls=ExtendedJSONCodec, indent=2)
    except OSError as exc:
        if log:
            log.warning('Could not write to auth file %s, error: %s', path, exc.strerror)
