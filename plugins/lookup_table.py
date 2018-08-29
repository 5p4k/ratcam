from plugins.base import Process, AVAILABLE_PROCESSES, PluginProcessBase
from plugins.singleton_host import SingletonHost
import inspect


class _PartialLookup:
    def _concat_keys(self, item):
        if isinstance(item, tuple) or isinstance(item, list):
            return tuple(self._prepend + list(item))
        else:
            return tuple(self._prepend + [item])

    def __getitem__(self, item):
        return self._parent[self._concat_keys(item)]

    __getattr__ = __getitem__

    def __init__(self, parent, prepend_keys):
        self._parent = parent
        if isinstance(prepend_keys, tuple) or isinstance(prepend_keys, list):
            self._prepend = list(prepend_keys)
        else:
            self._prepend = [prepend_keys]


class PluginLookupTable:
    @classmethod
    def _get_plugin_name(cls, spec):
        if isinstance(spec, str):
            return spec
        elif isinstance(spec, PluginProcessBase):
            return spec.get_remote_plugin_name()
        elif inspect.isclass(spec) and issubclass(spec, PluginProcessBase):
            return spec.plugin_name()
        return None

    @classmethod
    def _get_process(cls, spec):
        if isinstance(spec, Process):
            return spec
        elif spec in AVAILABLE_PROCESSES:
            return Process(spec)
        return None

    @classmethod
    def _normalize_keys(cls, tpl):
        assert isinstance(tpl, tuple) and len(tpl) == 2
        process = cls._get_process(tpl[0])
        if process is None:
            # Swap
            tpl = (tpl[1], tpl[0])
            process = cls._get_process(tpl[0])
            if process is None:
                raise ValueError(tpl[0], 'Cannot extract process from {}.'.format(tpl[0]))
        plugin_name = cls._get_plugin_name(tpl[1])
        if plugin_name is None:
            raise ValueError(tpl[1], 'Cannot extract plugin name from {}.'.format(tpl[1]))
        return process, plugin_name

    def __getitem__(self, item):
        if isinstance(item, tuple):
            if len(item) == 2:
                process, plugin_name = self.__class__._normalize_keys(item)
                return self._plugins[plugin_name][process]
            elif len(item) == 1:
                item = item[0]
            else:
                raise ValueError(item)
        # Item is only one. Is it a process?
        try_process = self.__class__._get_process(item)
        if try_process is not None:
            return _PartialLookup(self, (try_process,))
        # It must be a plugin name
        return self._plugins[self.__class__._get_plugin_name(item)]

    __getattr__ = __getitem__

    def __iter__(self):
        return iter(self.values())

    def __next__(self):
        return next(self.values())

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
