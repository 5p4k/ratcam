from .singleton_host import SingletonHost


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
