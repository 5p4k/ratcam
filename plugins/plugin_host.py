from plugins.singleton_host import SingletonHost
from plugins.base import Process, AVAILABLE_PROCESSES


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


class PluginTable:
    @classmethod
    def _normalize_keys(cls, tpl):
        assert isinstance(tpl, tuple) and len(tpl) == 2
        if isinstance(tpl[0], Process) or tpl[0] in AVAILABLE_PROCESSES:
            return Process(tpl[0]), str(tpl[1])
        elif isinstance(tpl[1], Process):
            return Process(tpl[1]), str(tpl[0])
        raise ValueError(tpl)


class PluginHost:
    def __enter__(self):
        self._host.__enter__()
        for plugin_name, plugin_type in self._plugin_process_instance_types.items():
            if plugin_type is None:
                continue
            self._plugin_process_instances[plugin_name] = self._host(plugin_type)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._plugin_process_instances = {k: None for k in self._plugin_process_instance_types.keys()}
        self._host.__exit__(exc_type, exc_val, exc_tb)

    @property
    def singleton_host(self):
        return self._host

    @property
    def plugin_instances(self):
        """
        :return: A dictionary mapping the plugin name to the plugin instance proxy object (or None, if the original type
        was None).
        """
        return self._plugin_process_instances

    def __init__(self, plugin_process_instance_types, socket, name=None):
        """
        :param plugin_process_instance_types: a dict object that maps the plugin name to the singleton type to
        instantiate for this plugin.
        :param socket: socket path for the hosting process.
        :param name: name of the hosting process.
        """
        self._plugin_process_instance_types = dict(plugin_process_instance_types)
        self._plugin_process_instances = {k: None for k in self._plugin_process_instance_types}
        self._host = SingletonHost(socket, name=name)
