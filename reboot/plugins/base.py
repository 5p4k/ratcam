from enum import Enum
from collections import namedtuple
from Pyro4 import oneway as pyro_expose_oneway


class Process(Enum):
    MAIN = 'main'
    TELEGRAM = 'telegram'
    CAMERA = 'camera'


_AVAILABLE_PROCESSES = [e.value for e in Process]


class ProcessPack(namedtuple('_ProcessPack', _AVAILABLE_PROCESSES)):
    def __getitem__(self, item):
        if isinstance(item, Process):
            return getattr(self, item.value)
        elif isinstance(item, str):
            return getattr(self, Process(item).value)
        return super(ProcessPack, self).__getitem__(item)

    def __setitem__(self, key, value):
        if isinstance(key, Process):
            setattr(self, key.value, value)
        elif isinstance(key, str):
            setattr(self, Process(key).value, value)
        super(ProcessPack, self).__setitem__(key, value)


class PluginProcessInstanceBase:
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

    @pyro_expose_oneway
    def activate(self, plugins, plugin_name, process):
        self._plugins = plugins
        self._plugin_name = plugin_name
        self._process = process
        self.__enter__()

    @pyro_expose_oneway
    def deactivate(self):
        self.__exit__(None, None, None)
        self._process = None
        self._plugin_name = None
        self._plugins = None

    def __init__(self):
        self._process = None
        self._plugin_name = None
        self._plugins = None
