import Pyro4
from .singleton_host import SingletonHost
from collections import namedtuple


_AVAILABLE_PROCESSES = ['main', 'telegram', 'camera']


class PluginBase:
    @property
    def host(self):
        return self._plugin_host

    @property
    def main_instance(self):
        return self._plugin_inst.main

    @property
    def telegram_instance(self):
        return self._plugin_inst.telegram

    @property
    def camera_instance(self):
        return self._plugin_inst.camera

    def activate(self, plugin_host, plugin_instance):
        self._plugin_host = plugin_host
        self._plugin_inst = plugin_instance

    def deactivate(self):
        self._plugin_inst = None
        self._plugin_host = None

    def __init__(self):
        self._plugin_host = None
        self._plugin_inst = None


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
                plugin.activate(self, plugin_instance)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for plugin_instance in self._plugin_inst.values():
            for plugin in plugin_instance:
                plugin.deactivate()
        self._plugin_inst = {}
        self._host.__exit__(exc_type, exc_val, exc_tb)

    @property
    def plugins(self):
        return self._plugins_inst

    def __init__(self, plugin_defs, *args, **kwargs):
        self._plugin_defs = {plugin.name: plugin for plugin in plugin_defs}
        self._plugin_inst = {}
        self._host = SingletonHost(*args, **kwargs)
