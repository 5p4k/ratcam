from .singleton_host import SingletonHost


class PluginProcessHost:
    def __enter__(self):
        self._host.__enter__()
        self._plugin_process_instances = {plugin_name: self._host(plugin_type) if plugin_type is not None else None
                                          for plugin_name, plugin_type in self._plugin_process_instance_types}
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._plugin_process_instances = {}
        self._host.__exit__(exc_type, exc_val, exc_tb)

    @property
    def instances(self):
        return self._plugin_process_instances

    def __init__(self, plugin_process_instance_types, socket, name=None):
        self._plugin_process_instance_types = plugin_process_instance_types
        self._plugin_process_instances = {}
        self._host = SingletonHost(socket, name=name)
