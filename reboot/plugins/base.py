import Pyro4
from .singleton_host import SingletonHost
from collections import namedtuple


_AVAILABLE_PROCESSES = ['main', 'telegram', 'camera']


class PluginInstance(namedtuple('_PluginInstance', _AVAILABLE_PROCESSES)):
    def __init__(self, *args, **kwargs):
        super(PluginInstance, self).__init__(*args, **kwargs)
        self.plugin_host = None


class PluginDefinition(namedtuple('_PluginDefinition', ['name'] + _AVAILABLE_PROCESSES)):
    def instantiate(self, host):
        return PluginInstance(*[host(entry) if entry is not None else None for entry in self[1:]])


@Pyro4.expose
class PluginHost:
    def __enter__(self):
        self._host.__enter__()
        self._plugin_inst = {plugin.name: plugin.instantiate(self._host) for plugin in self._plugin_defs}
        for plugin in self._plugin_inst.values():
            plugin.plugin_host = self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._host.__exit__(exc_type, exc_val, exc_tb)
        for plugin in self._plugin_inst.values():
            plugin.plugin_host = None
        self._plugin_inst = {}

    @property
    def plugins(self):
        return self._plugins_inst

    def __init__(self, plugin_defs, *args, **kwargs):
        self._plugin_defs = {plugin.name: plugin for plugin in plugin_defs}
        self._plugin_inst = {}
        self._host = SingletonHost(*args, **kwargs)
