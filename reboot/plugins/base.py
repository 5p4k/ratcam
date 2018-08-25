from enum import Enum
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway


class Process(Enum):
    MAIN = 'main'
    TELEGRAM = 'telegram'
    CAMERA = 'camera'


_AVAILABLE_PROCESSES = [e.value for e in Process]


class ProcessPack:
    def __getattr__(self, item):
        if item in _AVAILABLE_PROCESSES:
            return self[item]
        raise AttributeError(item)

    def __setattr__(self, key, value):
        if key in _AVAILABLE_PROCESSES:
            self[key] = value
        super(ProcessPack, self).__setattr__(key, value)

    def __getitem__(self, item):
        if isinstance(item, Process):
            return self._d[_AVAILABLE_PROCESSES.index(item.value)]
        elif isinstance(item, str):
            return self._d[_AVAILABLE_PROCESSES.index(item)]
        elif isinstance(item, int):
            return self._d[item]
        raise KeyError(item)

    def __setitem__(self, key, value):
        if isinstance(key, Process):
            self._d[_AVAILABLE_PROCESSES.index(key.value)] = value
        elif isinstance(key, str):
            self._d[_AVAILABLE_PROCESSES.index(key)] = value
        elif isinstance(key, int):
            self._d[key] = value
        else:
            raise KeyError(key)

    def __init__(self, *args, **kwargs):
        args = list(args[:len(_AVAILABLE_PROCESSES)])
        args = args + ([None] * (len(_AVAILABLE_PROCESSES) - len(args)))
        self._d = args
        for k, v in kwargs.items():
            if k in _AVAILABLE_PROCESSES:
                self[k] = v


class PluginProcessBase:
    @property
    def plugin_instance_pack(self):
        return self.plugins[self.plugin_name]

    @property
    def plugins(self):
        return self._plugins

    @property
    def plugin_name(self):
        return self._plugin_name

    @property
    def process(self):
        return self._process

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @pyro_expose
    @pyro_oneway
    def activate(self, plugins, plugin_name, process):
        self._plugins = plugins
        self._plugin_name = plugin_name
        # Need to explicitly convert because the serialization engine may not preserve the Enum
        self._process = Process(process)
        self.__enter__()

    @pyro_expose
    @pyro_oneway
    def deactivate(self):
        self.__exit__(None, None, None)
        self._process = None
        self._plugin_name = None
        self._plugins = None

    def __init__(self):
        self._process = None
        self._plugin_name = None
        self._plugins = None
