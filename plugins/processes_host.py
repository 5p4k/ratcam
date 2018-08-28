from tempfile import TemporaryDirectory
from plugins.base import Process, ProcessPack
from plugins.plugin_host import PluginHost
from plugins.lookup_table import PluginLookupTable
from Pyro4 import expose as pyro_expose
import os


_ACTIVE_PROCESS = None
_ACTIVE_PLUGINS = None


def active_process():
    global _ACTIVE_PROCESS
    return _ACTIVE_PROCESS


def active_plugins():
    global _ACTIVE_PLUGINS
    return _ACTIVE_PLUGINS


def find_plugin(*args):
    assert len(args) in [1, 2]
    return active_plugins()[tuple(args)]


class ProcessesHost:

    class _Housekeeper:
        @pyro_expose
        def setup(self, process, plugins):
            global _ACTIVE_PROCESS, _ACTIVE_PLUGINS
            if _ACTIVE_PROCESS is not None or _ACTIVE_PLUGINS is not None:
                raise RuntimeError('More than one PluginHost are using the same process!')
            assert isinstance(process, Process), 'You should be serializing using pickle on Pyro!'
            _ACTIVE_PROCESS = process
            _ACTIVE_PLUGINS = PluginLookupTable(plugins, process)

        @pyro_expose
        def teardown(self):
            global _ACTIVE_PROCESS, _ACTIVE_PLUGINS
            if _ACTIVE_PROCESS is None or _ACTIVE_PLUGINS is None:
                raise RuntimeError('More than one PluginHost are using the same process!')
            _ACTIVE_PROCESS = None
            _ACTIVE_PLUGINS = None

    @classmethod
    def _create_host(cls, socket_dir, plugin_definitions, process):
        """
        Creates a PluginProcessHost bound to a socket in socket_dir/process.sock, hosting plugin_definitions.
        :param socket_dir: Path to a folder where to set up a socket for this process.
        :param plugin_definitions: A dict object that maps the plugin name to the a ProcessPack of PluginProcessInstanceBase
        subclasses. Only the entry corresponding to process will be instantiated.
        :param process: Process to instatiate.
        :return: An instance of PluginProcessHost that will instantiate such PluginProcessInstanceBase subclasses upon
        context acquisition.
        """
        # Will not be created until host.__enter__
        socket = os.path.join(socket_dir, process.value + '.sock')
        # Plugin name -> plugin process instance type map
        plugin_process_instance_types = {plugin_name: plugin_types_pack[process]
                                         for plugin_name, plugin_types_pack in plugin_definitions.items()}
        # Instantiate it and give it the name explicitly
        return PluginHost(plugin_process_instance_types, socket=socket, name=process.value)

    def _activate_all_plugin_process_instances(self):
        for plugin_instance_pack in self.plugin_instances.values():
            for plugin_process_instance in filter(lambda x: x is not None, plugin_instance_pack.values()):
                plugin_process_instance.activate()

    def _deactivate_all_plugin_process_instances(self):
        for plugin_name, plugin_instance_pack in self.plugin_instances.items():
            for plugin_process_instance in filter(lambda x: x is not None, plugin_instance_pack.values()):
                plugin_process_instance.deactivate()

    @property
    def plugin_instances(self):
        """
        :return: A dictionary that maps the plugin name to a ProcessPack. If this is called in a runtime context where
        this PluginProcesses instance is active, the ProcessPack contains three Pyro4 proxies to the instances residing
        on the processes. Otherwise, the ProcessPack contains None.
        """
        return self._plugin_instances

    def __enter__(self):
        # Create temp dir
        self._socket_dir.__enter__()
        # Activate all hosts in sequence
        for host in self._plugin_process_host_pack.values():
            host.__enter__()
        # Collect all plugin instances
        for plugin_name in self._plugin_instances.keys():
            self._plugin_instances[plugin_name] = ProcessPack(*[
                self._plugin_process_host_pack[process].plugin_instances[plugin_name] for process in Process
            ])
        # Change the running process variable in the remote process and publish a list of plugins
        for process, host in self._plugin_process_host_pack.items():
            self._housekeepers[process] = host.singleton_host(ProcessesHost._Housekeeper)
            self._housekeepers[process].setup(process, self._plugin_instances)
        # Activate all plugin instances with the information about all plugins
        self._activate_all_plugin_process_instances()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reverse destruction order as __enter__
        self._deactivate_all_plugin_process_instances()
        # Remove the list of plugins
        for process in Process:
            self._housekeepers[process].teardown()
            self._housekeepers[process] = None
        # Destroy all plugins
        for plugin_name in self._plugin_instances.keys():
            self._plugin_instances[plugin_name] = None
        # Deactivate all hosts
        for host in self._plugin_process_host_pack.values():
            host.singleton_host.initiate_shutdown()
        for host in self._plugin_process_host_pack.values():
            host.__exit__(exc_type, exc_val, exc_tb)
        # Destroy all dirs
        self._socket_dir.__exit__(exc_type, exc_val, exc_tb)

    def __init__(self, plugins):
        """
        :param plugins: dict-like object that maps plugin name in the process instance types. The key type is string,
        and the value type is a ProcessPack containing three types, subclasses of PluginProcessInstanceBase. Is it ok
        for the ProcessPack to contain None entries. For example
            plugins = {'root_plugin': ProcessPack(None, None, MySubclassOfPluginProcessInstanceBase)}
        """
        self._socket_dir = TemporaryDirectory()
        self._plugin_instances = dict({k: None for k in plugins})
        self._plugin_process_host_pack = ProcessPack(*[
            self.__class__._create_host(self._socket_dir.name, plugins, process)
            for process in Process
        ])
        self._housekeepers = ProcessPack()
