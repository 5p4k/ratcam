from plugins.base import Process, AVAILABLE_PROCESSES, PluginProcessBase, ProcessPack
from plugins.singleton_host import SingletonHost
import inspect


class PluginLookupDict(dict):
    @classmethod
    def extract_plugin_name(cls, spec):
        if isinstance(spec, str):
            return spec
        elif isinstance(spec, PluginProcessBase):
            return spec.get_remote_plugin_name()
        elif inspect.isclass(spec) and issubclass(spec, PluginProcessBase):
            return spec.plugin_name()
        return None

    def __getitem__(self, item):
        retval = self.get(item, None)
        if retval is None:
            return self.get(self.__class__.extract_plugin_name(item))
        return retval

    __getattr__ = __getitem__


class PluginLookupTable:
    def __getitem__(self, item):
        if isinstance(item, tuple):
            if len(item) == 2:
                return self[item[0]][item[1]]
            elif len(item) == 1:
                item = item[0]
            else:
                raise KeyError(item)
        # Item is only one. Is it a process?
        if isinstance(item, Process) or item in AVAILABLE_PROCESSES:
            return self._plugins_by_process[Process(item)]
        # It must be a plugin name
        return self._plugins[PluginLookupDict.extract_plugin_name(item)]

    __getattr__ = __getitem__

    def __iter__(self):
        return iter(self.values())

    def values(self):
        return self._plugins.values()

    def items(self):
        return self._plugins.items()

    def keys(self):
        return self._plugins.keys()

    def _replace_local_instances(self, process):
        for plugin in self._plugins.values():
            if plugin[process] is None:
                continue
            # Try to get the id and replace
            plugin_id = plugin[process].get_remote_id()
            if plugin_id in SingletonHost.local_singletons_by_id():
                plugin[process] = SingletonHost.local_singletons_by_id()[plugin_id]

    def __init__(self, plugins, process):
        self._plugins = plugins
        self._replace_local_instances(process)
        self._plugins_by_process = ProcessPack(*[
            PluginLookupDict({k: v[p] for k, v in self._plugins.items()}) for p in Process
        ])
