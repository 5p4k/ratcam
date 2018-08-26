# https://stackoverflow.com/a/13520518/1749822
class DotDict(dict):
    __delattr__ = dict.__delitem__

    def __setattr__(self, key, value):
        if isinstance(value, dict):
            value = DotDict(value)
        self[key] = value

    def __getattr__(self, item):
        return self.get(item, None)

    def __init__(self, dct):
        super(DotDict, self).__init__(dct)
        for key, value in self.items():
            if isinstance(value, dict):
                self[key] = DotDict(value)

    def to_dict_tree(self):
        return dict({k: v.to_dict_tree() if isinstance(v, DotDict) else v for k, v in self.items()})
