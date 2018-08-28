from plugins.base import ProcessPack, Process, PluginProcessBase


_PLUGINS = {}


def _update_pack(pack, **kwargs):
    return ProcessPack(*[pack[k] if k.value not in kwargs else kwargs[k.value] for k in Process])


class _MakePlugin:
    def _ensure_process(self, cls):
        if cls.process.__func__ is PluginProcessBase.process.__func__:
            if self._process is None:
                raise ValueError('The class {} does not provide a process class method and no explicit process '
                                 'was set.'.format(cls.__name__))
            cls.process = classmethod(lambda _: self._process)
        elif self._process is None:
            self._process = cls.process()
        elif cls.process() != self._process:
            raise ValueError('The class {} defines a process that is different than the one explicitly stated '
                             'by make_plugin.'.format(cls.__name__))

    def _ensure_plugin_name(self, cls):
        if cls.plugin_name.__func__ is PluginProcessBase.plugin_name.__func__:
            if self._name is None:
                raise ValueError('The class {} does not provide a plugin_name class method and no explicit plugin_name '
                                 'was set.'.format(cls.__name__))
            cls.plugin_name = classmethod(lambda _: self._name)
        elif self._name is None:
            self._name = cls.plugin_name()
        elif cls.plugin_name() != self._name:
            raise ValueError('The class {} defines a plugin_name that is different than the one explicitly stated '
                             'by make_plugin.'.format(cls.__name__))

    def __call__(self, cls):
        if not issubclass(cls, PluginProcessBase):
            raise ValueError('A class need to be subclass of PluginProcessInstanceBase to be instantiable.')
        self._ensure_plugin_name(cls)
        self._ensure_process(cls)
        register(cls, self._name, self._process)
        return cls

    def __init__(self, plugin_name=None, process=None):
        self._name = plugin_name
        self._process = process


make_plugin = _MakePlugin


def get_all_plugins():
    global _PLUGINS
    return dict({k: v for k, v in _PLUGINS.items()})


def register(plugin_cls, name, process):
    global _PLUGINS
    if name not in _PLUGINS:
        _PLUGINS[name] = ProcessPack(None, None, None)
    _PLUGINS[name] = _update_pack(_PLUGINS[name], **{process.value: plugin_cls})
