from enum import Enum
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway
import Pyro4
from plugins.singleton_host import SingletonHost
from plugins.processes_host import ProcessesHost


class Process(Enum):
    MAIN = 'main'
    TELEGRAM = 'telegram'
    CAMERA = 'camera'


AVAILABLE_PROCESSES = [e.value for e in Process]


class ProcessPack:
    def __getattr__(self, item):
        if item in AVAILABLE_PROCESSES:
            return self[item]
        raise AttributeError(item)

    def __setattr__(self, key, value):
        if key in AVAILABLE_PROCESSES:
            self[key] = value
        super(ProcessPack, self).__setattr__(key, value)

    def __getitem__(self, item):
        if isinstance(item, Process):
            return self._d[AVAILABLE_PROCESSES.index(item.value)]
        elif isinstance(item, str):
            return self._d[AVAILABLE_PROCESSES.index(item)]
        elif isinstance(item, int):
            return self._d[item]
        raise KeyError(item)

    def __setitem__(self, key, value):
        if isinstance(key, Process):
            self._d[AVAILABLE_PROCESSES.index(key.value)] = value
        elif isinstance(key, str):
            self._d[AVAILABLE_PROCESSES.index(key)] = value
        elif isinstance(key, int):
            self._d[key] = value
        else:
            raise KeyError(key)

    def items(self):
        for process in Process:
            yield process, self[process]

    def values(self):
        yield from self._d

    def __init__(self, *args, **kwargs):
        args = list(args[:len(AVAILABLE_PROCESSES)])
        args = args + ([None] * (len(AVAILABLE_PROCESSES) - len(args)))
        self._d = args
        for k, v in kwargs.items():
            if k in AVAILABLE_PROCESSES:
                self[k] = v


class PluginProcessBase:
    @pyro_expose
    def get_obj_id(self):
        return id(self)

    def _replace_local_plugin_instances(self):
        cur_process = ProcessesHost.current_process()
        for plugin in self._plugins.values():
            if plugin[cur_process] is None:
                continue
            # Try to get the id and replace
            plugin_id = plugin[cur_process].get_obj_id()
            if plugin_id in SingletonHost.local_singletons_by_id():
                plugin[cur_process] = SingletonHost.local_singletons_by_id()[plugin_id]

    @property
    def plugin_instance_pack(self):
        return self.plugins[self.plugin_name]

    @property
    def plugins(self):
        return self._plugins

    @property
    def plugin_name(self):
        return self._plugin_name

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @pyro_expose
    @pyro_oneway
    def activate(self, plugins, plugin_name):
        assert all(map(lambda plugin_pack: isinstance(plugin_pack, ProcessPack), plugins.values())), \
            'You called PluginProcessBase.activate via Pyro, but the Process object was downcasted to a string. You ' \
            'may have configured the wrong Pyro serializer. The current Pyro serializer is ' + \
            Pyro4.config.SERIALIZER + ' and the only serializer that can send correctly an Enum (or ProcessPack, ' \
                                      'which is also needed) is pickle.'
        self._plugins = plugins
        self._plugin_name = plugin_name
        self._replace_local_plugin_instances()
        self.__enter__()

    @pyro_expose
    @pyro_oneway
    def deactivate(self):
        self.__exit__(None, None, None)
        self._plugin_name = None
        self._plugins = None

    def __init__(self):
        self._plugin_name = None
        self._plugins = None
