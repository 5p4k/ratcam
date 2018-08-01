import Pyro4
from .singleton_host import SingletonHost
from collections import namedtuple


_AVAILABLE_PROCESSES = ['main', 'telegram', 'camera']


class PluginBase:
    def activate(self, plugin_host):
        pass

    def deactivate(self):
        pass


class PluginInstance(namedtuple('_PluginInstance', _AVAILABLE_PROCESSES)):
    pass


class PluginDefinition(namedtuple('_PluginDefinition', ['name'] + _AVAILABLE_PROCESSES)):
    def assert_valid_types(self):
        for k in _AVAILABLE_PROCESSES:
            process_class = getattr(self, k, None)
            if process_class is not None:
                assert(issubclass(process_class, PluginBase))

    def instantiate(self, host):
        self.assert_valid_types()
        return PluginInstance(*[host(entry) if entry is not None else None for entry in self[1:]])


@Pyro4.expose
class PluginHost:
    def __enter__(self):
        self._host.__enter__()
        self._plugin_inst = {plugin.name: plugin.instantiate(self._host) for plugin in self._plugin_defs}
        for plugin_instance in self._plugin_inst.values():
            for plugin in plugin_instance:
                plugin.activate(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._host.__exit__(exc_type, exc_val, exc_tb)
        for plugin_instance in self._plugin_inst.values():
            for plugin in plugin_instance:
                plugin.deactivate()
        self._plugin_inst = {}

    @property
    def plugins(self):
        return self._plugins_inst

    def __init__(self, plugin_defs, *args, **kwargs):
        self._plugin_defs = {plugin.name: plugin for plugin in plugin_defs}
        self._plugin_inst = {}
        self._host = SingletonHost(*args, **kwargs)
