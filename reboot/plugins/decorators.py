from .base import ProcessPack, Process, PluginProcessBase


_plugins = {}


def _update_pack(pack, **kwargs):
    return ProcessPack(*[pack[k] if k.value not in kwargs else kwargs[k.value] for k in Process])


class _MakePlugin:
    def __call__(self, cls):
        if not issubclass(cls, PluginProcessBase):
            raise ValueError('A class need to be subclass of PluginProcessInstanceBase to be instantiable.')
        global _plugins
        if self._name not in _plugins:
            _plugins[self._name] = ProcessPack(None, None, None)
        _plugins[self._name] = _update_pack(_plugins[self._name], **{self._process.value: cls})
        return cls

    def __init__(self, plugin_name, process):
        self._name = plugin_name
        self._process = process


make_plugin = _MakePlugin


def get_all_plugins():
    global _plugins
    return {k: v for k, v in _plugins.items()}
