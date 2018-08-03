from tempfile import TemporaryDirectory
from .base import Process, ProcessPack
from .plugin_process_host import PluginProcessHost
import os


DEFAULT_PROCESS_HOSTS = ProcessPack(PluginProcessHost, PluginProcessHost, PluginProcessHost)


class PluginProcesses:
    @classmethod
    def _create_host(cls, host_type_pack, socket_dir, plugin_types, process):
        # Will not be created until host.__enter__
        socket = os.path.join(socket_dir, process.value + '.sock')
        # Plugin name -> plugin process instance type map
        plugin_process_instance_types = {plugin_type.name: plugin_type.process_instance_types[process]
                                         for plugin_type in plugin_types}
        host_type = host_type_pack[process]
        # Instantiate it and give it the name explicitly
        return host_type(plugin_process_instance_types, socket=socket, name=process.value)

    def _activate_all_plugin_process_instances(self):
        all_plugins = dict({plugin_name: plugin.process_instance_pack for plugin_name, plugin in self.plugins.items()})
        for plugin_name, plugin in self.plugins.items():
            for process in Process:
                plugin_process_instance = plugin.process_instance_pack[process]
                if plugin_process_instance is None:
                    continue
                plugin_process_instance.activate(plugin_name, process, plugin.process_instance_pack, all_plugins)

    def _deactivate_all_plugin_process_instances(self):
        for plugin in self.plugins.values():
            for plugin_process_instance in plugin.process_instance_pack:
                if plugin_process_instance is None:
                    continue
                plugin_process_instance.deactivate()

    def _get_plugin_process_instance_pack(self, plugin_name):
        return ProcessPack(*[self._plugin_process_host_pack[process].instances[plugin_name] for process in Process])

    def __enter__(self):
        # Create temp dir
        self._socket_dir.__enter__()
        # Activate all hosts in sequence
        for host in self._plugin_process_host_pack.values():
            host.__enter__()
        # Create all plugin instances
        for plugin_name, plugin_type in self._plugins.items():
            # Replace the type of the plugin with an instance of the same type with the right host and instance pack
            self._plugins[plugin_name] = plugin_type(self._get_plugin_process_instance_pack(plugin_name))
        self._activate_all_plugin_process_instances()

    @property
    def plugins(self):
        return self._plugins

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reverse destruction order as __enter__
        self._deactivate_all_plugin_process_instances()
        # Destroy all plugins
        for plugin_name, plugin in self._plugins.items():
            # Replace each instance of the plugin with the type that generated it
            self._plugins[plugin_name] = type(plugin)
        for host in self._plugin_process_host_pack.values():
            host.__exit__(exc_type, exc_val, exc_tb)
        self._socket_dir.__exit__(exc_type, exc_val, exc_tb)

    def __init__(self, plugin_types, host_type_pack=DEFAULT_PROCESS_HOSTS):
        self._socket_dir = TemporaryDirectory()
        self._plugins = {plugin_type.name: plugin_type for plugin_type in plugin_types}
        self._plugin_process_host_pack = ProcessPack(*[
            self.__class__._create_host(host_type_pack, self._socket_dir.name, plugin_types, process)
            for process in Process
        ])
