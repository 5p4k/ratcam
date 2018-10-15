from enum import Enum
from Pyro4 import expose as pyro_expose
import logging


_log = logging.getLogger('plugin_base')


class Process(Enum):
    MAIN = 'main'
    TELEGRAM = 'telegram'
    CAMERA = 'camera'


AVAILABLE_PROCESSES = [e.value for e in Process]


class ProcessPack:
    def __getattr__(self, item):
        if item in AVAILABLE_PROCESSES:
            return self[item]
        raise AttributeError(item)

    def __setattr__(self, key, value):
        if key in AVAILABLE_PROCESSES:
            self[key] = value
        super(ProcessPack, self).__setattr__(key, value)

    def __getitem__(self, item):
        if isinstance(item, Process):
            return self._d[AVAILABLE_PROCESSES.index(item.value)]
        elif isinstance(item, str):
            return self._d[AVAILABLE_PROCESSES.index(item)]
        raise KeyError(item)

    def __setitem__(self, key, value):
        if isinstance(key, Process):
            self._d[AVAILABLE_PROCESSES.index(key.value)] = value
        elif isinstance(key, str):
            self._d[AVAILABLE_PROCESSES.index(key)] = value
        else:
            raise KeyError(key)

    def items(self):
        for process in Process:
            yield process, self[process]

    def values(self):
        yield from self._d

    def nonempty_values(self):
        yield from [entry for entry in self._d if entry is not None]

    def __iter__(self):
        return iter(self.values())

    def __init__(self, *args, **kwargs):
        args = list(args[:len(AVAILABLE_PROCESSES)])
        args = args + ([None] * (len(AVAILABLE_PROCESSES) - len(args)))
        self._d = args
        for k, v in kwargs.items():
            if k in AVAILABLE_PROCESSES:
                self[k] = v


class PluginProcessBase:
    @classmethod
    def plugin_name(cls):  # pragma: no cover
        return None

    @classmethod
    def process(cls):  # pragma: no cover
        return None

    @pyro_expose
    def get_remote_id(self):
        return id(self)

    @pyro_expose
    def get_remote_plugin_name(self):
        return self.__class__.plugin_name()

    @pyro_expose
    def get_remote_process(self):
        return self.__class__.process()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @pyro_expose
    def activate(self):
        try:
            self.__enter__()
        except Exception as e:  # pragma: no cover
            # This doesn't need to be covered by testing, we use it for debugging only
            _log.exception('Unable to activate %s.', self.get_remote_plugin_name())
            raise e

    @pyro_expose
    def deactivate(self):
        try:
            self.__exit__(None, None, None)
        except Exception as e:  # pragma: no cover
            # This doesn't need to be covered by testing, we use it for debugging only
            _log.exception('Unable to deactivate %s.', self.get_remote_plugin_name())
            raise e
