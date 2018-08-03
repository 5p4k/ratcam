from enum import Enum
from collections import namedtuple
from Pyro4 import oneway


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
    def instances_pack(self):
        return self._instances_pack

    @property
    def all_plugins(self):
        return self._all_plugins

    @property
    def plugin_name(self):
        return self._plugin_name

    def _activate(self):
        pass

    def _deactivate(self):
        pass

    @oneway
    def activate(self, plugin_name, instances_pack, all_plugins):
        self._plugin_name = plugin_name
        self._instances_pack = instances_pack
        self._all_plugins = all_plugins
        self._activate()

    @oneway
    def deactivate(self):
        self._deactivate()
        self._plugin_name = None
        self._all_plugins = None
        self._instances_pack = None

    def __init__(self):
        self._plugin_name = None
        self._all_plugins = None
        self._instances_pack = None


class PluginBase:
    name = None
    process_instance_types = ProcessPack(None, None, None)

    @property
    def process_instance_pack(self):
        return self._process_instance_pack

    def __init__(self, process_instance_pack):
        self._process_instance_pack = process_instance_pack
