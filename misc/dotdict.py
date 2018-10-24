# https://stackoverflow.com/a/13520518/1749822
class DotDict:
    _PASSTHROUGH_MEMBERS = ('_d', '_parent_and_key')

    def __delattr__(self, item):
        if item in self._d:
            del self._d[item]

    def __getattr__(self, item):
        if item in DotDict._PASSTHROUGH_MEMBERS:
            return super(DotDict, self).__getattr__(item)
        if item in self._d:
            retval = self._d[item]
            if isinstance(retval, dict):
                retval = DotDict(retval)
                self._d[item] = retval
            return retval
        else:
            return DotDict({}, (self, item))

    def __setattr__(self, key, value):
        if key in DotDict._PASSTHROUGH_MEMBERS:
            super(DotDict, self).__setattr__(key, value)
            return
        self._d[key] = value
        if self._parent_and_key is not None:
            setattr(*self._parent_and_key, self._d)
            self._parent_and_key = None

    def __contains__(self, item):
        return item in self._d

    def __iter__(self):
        return iter(self._d)

    def items(self):
        for k in self:
            yield k, getattr(self, k)

    def values(self):
        for k in self:
            yield getattr(self, k)

    def get(self, key, default=None, cast_to_type=None, ge=None, le=None, sanitizer=None):
        if key in self:
            retval = getattr(self, key)
            if cast_to_type is not None:
                # noinspection PyBroadException
                try:
                    retval = cast_to_type(retval)
                except:
                    retval = default
        else:
            retval = default
        if sanitizer is not None:
            retval = sanitizer(retval)
        if retval is not None and ge is not None:
            retval = max(retval, ge)
        if retval is not None and le is not None:
            retval = min(retval, le)
        return retval

    def __init__(self, d, parent_and_key=None):
        self._d = d
        self._parent_and_key = parent_and_key

    def _downcast_and_get_d(self):
        for k, v in self._d.items():
            if isinstance(v, DotDict):
                self._d[k] = v._downcast_and_get_d()
        return self._d

    def get_storage(self, downcast=True):
        if downcast:
            self._downcast_and_get_d()
        return self._d
