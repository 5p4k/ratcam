import types


_HANDLERS_CLS_PROP_NAME = '_HANDLERS'


class DelayedHandlerConstructor:
    def get_handler_method(self, handler_target=None):
        if callable(self.handler):
            if handler_target:
                return types.MethodType(self.handler, handler_target)
            return self.handler
        elif isinstance(self.handler, str) and handler_target:
            return getattr(handler_target, self.handler)
        raise RuntimeError('Unable to bind or to use specified handler {} on '
                           'target {}.'.format(self.handler, handler_target), self.handler, handler_target)

    def __call__(self, handler_target=None):
        return self.handler_cls(handler_target, self.get_handler_method(handler_target), *self.args, **self.kwargs)

    def __init__(self, handler, handler_cls, *args, **kwargs):
        self.handler = handler
        self.handler_cls = handler_cls
        self.args = args
        self.kwargs = kwargs


def make_handler(handler_cls, *args, **kwargs):
    return lambda fn: DelayedHandlerConstructor(fn, handler_cls, *args, **kwargs)


class HandlerMeta(type):
    def __new__(mcs, name, bases, attrs):
        # Collect here the cctors
        handlers = attrs.get(_HANDLERS_CLS_PROP_NAME, [])
        if not isinstance(handlers, list):
            raise RuntimeError('The {} property must be a list.'.format(_HANDLERS_CLS_PROP_NAME))
        # Restore the unbound method in the attributes that are wrapped in DelayedHandlerConstructor
        for k in attrs.keys():
            v = attrs[k]
            if isinstance(v, DelayedHandlerConstructor):
                handlers.append(v)
                attrs[k] = v.handler
        attrs[_HANDLERS_CLS_PROP_NAME] = handlers
        return super(HandlerMeta, mcs).__new__(mcs, name, bases, attrs)


class HandlerBase(metaclass=HandlerMeta):
    @property
    def handlers(self):
        return iter(self._handlers)

    def __init__(self):
        self._handlers = []
        # Bind all the handlers
        for handler_cctor in getattr(self.__class__, _HANDLERS_CLS_PROP_NAME):
                self._handlers.append(handler_cctor(self))
