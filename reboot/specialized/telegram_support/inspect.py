import inspect
import types


def get_cls_of_method(f):
    # https://stackoverflow.com/a/25959545/1749822
    return getattr(inspect.getmodule(f), f.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0])


def bind_method(self, f):
    return types.MethodType(f, self, self.__class__)
