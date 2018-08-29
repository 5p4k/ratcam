from enum import Enum
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway


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

    def __next__(self):
        return next(self.values())

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
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @pyro_expose
    @pyro_oneway
    def activate(self):
        self.__enter__()

    @pyro_expose
    @pyro_oneway
    def deactivate(self):
        self.__exit__(None, None, None)
