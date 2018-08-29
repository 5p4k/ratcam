import unittest
from plugins.base import ProcessPack, Process, PluginProcessBase
from plugins.processes_host import ProcessesHost
from specialized.plugin_media_manager import MediaManagerPlugin, MediaReceiver, MEDIA_MANAGER_PLUGIN_NAME
from Pyro4 import expose as pyro_expose
import tempfile
import os
from threading import Event
import time


class RemoteMediaManager(MediaManagerPlugin):
    @pyro_expose
    def test_deliver_media(self, path, kind=None, info=None):
        self.deliver_media(path, kind, info)


class TestMediaManager(unittest.TestCase):
    def retry_until_timeout(self, fn, timeout=1., sleep_step=0.001):  # pragma: no cover
        sleep_time = sleep_step
        start_time = time.time()
        while time.time() - start_time < timeout:
            if fn():
                return True
            time.sleep(sleep_time)
            sleep_time += sleep_step
        self.fail()

    def test_simple(self):
        with ProcessesHost({MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=RemoteMediaManager)}) as phost:
            self.assertIn(MEDIA_MANAGER_PLUGIN_NAME, phost.plugin_instances)
            self.assertIsNotNone(phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main)

    def test_file_deletion(self):
        with ProcessesHost({MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=RemoteMediaManager)}) as phost:
            with tempfile.NamedTemporaryFile(delete=False) as media_file:
                path = media_file.name
            assert os.path.isfile(path)
            phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main.test_deliver_media(path, None)
        self.assertFalse(os.path.isfile(path))

    class ControlledMediaReceiver(PluginProcessBase, MediaReceiver):
        @classmethod
        def plugin_name(cls):  # pragma: no cover
            return 'ControlledMediaReceiver'

        @classmethod
        def process(cls):  # pragma: no cover
            return Process.MAIN

        def handle_media(self, media):
            self._media = media
            self._let_go_of_media.wait()

        @pyro_expose
        def let_media_go(self):
            self._let_go_of_media.set()

        @pyro_expose
        @property
        def media(self):
            return self._media

        def __init__(self):
            self._media = None
            self._let_go_of_media = Event()

    def test_media_dispatch(self):
        plugins = {
            TestMediaManager.ControlledMediaReceiver.plugin_name():
                ProcessPack(main=TestMediaManager.ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=RemoteMediaManager)
        }
        with ProcessesHost(plugins) as phost:
            with tempfile.NamedTemporaryFile(delete=False) as media_file:
                path = media_file.name
            media_mgr = phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main
            media_rcv = phost.plugin_instances[TestMediaManager.ControlledMediaReceiver.plugin_name()].main
            media_mgr.test_deliver_media(path, 'mp4', 45)
            # Make sure it gets delivered
            if self.retry_until_timeout(lambda: media_rcv.media is not None):
                self.assertTrue(os.path.isfile(path))
                self.assertEqual(media_rcv.media.path, path)
                self.assertEqual(media_rcv.media.kind, 'mp4')
                self.assertEqual(media_rcv.media.info, 45)
                self.assertEqual(media_rcv.media.owning_process, Process.MAIN)
                time.sleep(0.5)
                self.assertTrue(os.path.isfile(path))
                media_rcv.let_media_go()
                self.retry_until_timeout(lambda: not os.path.isfile(path))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
