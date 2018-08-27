from plugins.base import Process, AVAILABLE_PROCESSES, PluginProcessBase
from plugins.singleton_host import SingletonHost


class _PartialLookup:
    def _concat_keys(self, item):
        if isinstance(item, tuple) or isinstance(item, list):
            return tuple(self._prepend + list(item))
        else:
            return tuple(self._prepend + [item])

    def __getitem__(self, item):
        return self._parent[self._concat_keys(item)]

    def __setitem__(self, key, value):
        self._parent[self._concat_keys(key)] = value

    __setattr__ = __setitem__
    __getattr__ = __getitem__

    def __init__(self, parent, prepend_keys):
        self._parent = parent
        if isinstance(prepend_keys, tuple) or isinstance(prepend_keys, list):
            self._prepend = list(prepend_keys)
        else:
            self._prepend = [prepend_keys]


class PluginLookupTable:
    @classmethod
    def _normalize_keys(cls, tpl):
        assert isinstance(tpl, tuple) and len(tpl) == 2
        plugin_name = None
        if not isinstance(tpl[0], Process) and tpl[0] not in AVAILABLE_PROCESSES:
            tpl = (tpl[1], tpl[0])
        if isinstance(tpl[1], str):
            plugin_name = tpl[1]
        elif isinstance(tpl[1], PluginProcessBase):
            plugin_name = tpl[1].get_remote_plugin_name()
        elif issubclass(tpl[1], PluginProcessBase):
            plugin_name = tpl[1].plugin_name()
        if plugin_name is None:
            raise ValueError(tpl[1])
        return Process(tpl[0]), plugin_name

    def __getitem__(self, item):
        if isinstance(item, tuple) and len(item) == 2:
            process, plugin_name = self.__class__._normalize_keys(item)
            return self._plugins[plugin_name][process]
        else:
            return _PartialLookup(self, (item,))

    def _replace_local_instances(self, process):
        for plugin in self._plugins.values():
            if plugin[process] is None:
                continue
            # Try to get the id and replace
            plugin_id = plugin[process].get_remote_id()
            if plugin_id in SingletonHost.local_singletons_by_id():
                plugin[process] = SingletonHost.local_singletons_by_id()[plugin_id]

    def __init__(self, plugins, process):
        self._plugins = dict(plugins)
        self._replace_local_instances(process)
