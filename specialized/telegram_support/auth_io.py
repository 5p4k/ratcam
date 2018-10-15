import os
import json
from specialized.telegram_support.auth import ChatAuthStorage
from misc.extended_json_codec import ExtendedJSONCodec


def load_chat_auth_storage(path, log=None):
    def _discard_data():  # pragma: no cover
        if log:
            log.error('Data will be discarded.')
        # noinspection PyBroadException
        try:
            os.rename(path, path + '.malformed')
        except:
            if log:
                log.exception('Unable to move %s.', path)

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
        except OSError:  # pragma: no cover
            if log:
                log.exception('Could not load auth file %s.', path)
        except json.JSONDecodeError as exc:  # pragma: no cover
            if log:
                log.exception('Malformed JSON auth file %s:%d:d, error: %s', path, exc.lineno, exc.colno, exc.msg)
            _discard_data()

    return ChatAuthStorage()


def save_chat_auth_storage(path, chat_auth_storage, log=None):
    path = os.path.abspath(path)
    try:
        with open(path, 'w') as fp:
            json.dump(chat_auth_storage, fp, cls=ExtendedJSONCodec, indent=2)
    except OSError:  # pragma: no cover
        if log:
            log.exception('Could not write to auth file %s.', path)
