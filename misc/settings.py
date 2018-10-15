import os
import json
from misc.extended_json_codec import ExtendedJSONCodec
from misc.dotdict import DotDict


SETTINGS = DotDict({})


def load_settings(path, log=None):
    global SETTINGS

    def _discard_data():  # pragma: no cover
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
            SETTINGS = DotDict(json_data)
        except OSError:  # pragma: no cover
            if log:
                log.exception('Could not load settings file %s.', path)
        except json.JSONDecodeError as exc:  # pragma: no cover
            if log:
                log.exception('Malformed JSON settings file %s:%d:d, error: %s', path, exc.lineno, exc.colno, exc.msg)
            _discard_data()
    return SETTINGS


def save_settings(path, log=None):
    global SETTINGS
    path = os.path.abspath(path)
    try:
        with open(path, 'w') as fp:
            json.dump(SETTINGS.to_dict_tree(), fp, cls=ExtendedJSONCodec, indent=2)
    except OSError:  # pragma: no cover
        if log:
            log.exception('Could not write to settings file %s.', path)


load_settings(os.path.join(os.path.dirname(__file__), 'default.json'))
