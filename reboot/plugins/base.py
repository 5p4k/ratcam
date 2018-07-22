import Pyro4


class PluginProcessBase:
    @property
    def main_process(self):
        return self._main

    @property
    def camera_process(self):
        return self._camera

    @property
    def telegram_process(self):
        return self._telegram

    def setup(self, main_uri, camera_uri, telegram_uri, *_, **__):
        if self._main is not None or self._camera is not None or self._telegram is not None:
            raise RuntimeError('Called {}.setup several times is not allowed.'.format(self.__class__.__name__))
        self._main = Pyro4.Proxy(main_uri)
        self._camera = Pyro4.Proxy(camera_uri) if camera_uri is not None else None
        self._telegram = Pyro4.Proxy(telegram_uri) if telegram_uri is not None else None

    def __init__(self):
        self._main = None
        self._camera = None
        self._telegram = None


class PluginMainProcessBase(PluginProcessBase):
    pass


class PluginTelegramProcessBase(PluginProcessBase):
    pass


class PluginCameraProcessBase(PluginProcessBase):
    pass
