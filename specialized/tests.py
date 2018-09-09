import unittest
from plugins.base import ProcessPack, Process, PluginProcessBase
from plugins.decorators import make_plugin
from plugins.processes_host import ProcessesHost
from specialized.plugin_media_manager import MediaManagerPlugin, MediaReceiver, MEDIA_MANAGER_PLUGIN_NAME, Media
from Pyro4 import expose as pyro_expose
import tempfile
import os
from threading import Event
import time
from specialized.plugin_picamera import PiCameraProcessBase, PICAMERA_ROOT_PLUGIN_NAME, PiCameraRootPlugin
from misc.cam_replay import PiCameraReplay, load_demo_events
from plugins.processes_host import find_plugin
from uuid import UUID
from specialized.plugin_buffered_recorder import BufferedRecorderPlugin, BUFFERED_RECORDER_PLUGIN_NAME


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

    def test_spurious_consume_calls(self):
        plugins = {
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=MediaManagerPlugin)
        }
        dummy_media = Media(
            UUID('4b878c8a-de5a-402b-9f9b-127f5a3a78de'),
            Process.MAIN,
            None,
            None,
            None
        )
        with ProcessesHost(plugins) as phost:
            media_mgr = phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main
            # Nothing should happen here
            media_mgr.consume_media(dummy_media, Process.MAIN)
            media_mgr.consume_media(dummy_media, Process.CAMERA)
            another_dummy_media = Media(dummy_media.uuid, Process.TELEGRAM, None, None, None)
            media_mgr.consume_media(another_dummy_media, Process.TELEGRAM)
            media_mgr.consume_media(another_dummy_media, Process.MAIN)
            media_mgr.consume_media(another_dummy_media, Process.CAMERA)

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

    def test_manual_dispatch(self):
        plugins = {
            TestMediaManager.ControlledMediaReceiver.plugin_name():
                ProcessPack(main=TestMediaManager.ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=MediaManagerPlugin)
        }
        dummy_media = Media(
            UUID('4b878c8a-de5a-402b-9f9b-127f5a3a78de'),
            Process.CAMERA,
            'KIND',
            'PATH',
            'INFO'
        )
        with ProcessesHost(plugins) as phost:
            media_mgr = phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main
            media_rcv = phost.plugin_instances[TestMediaManager.ControlledMediaReceiver.plugin_name()].main
            media_mgr.dispatch_media(dummy_media)
            # Make sure it gets delivered
            if self.retry_until_timeout(lambda: media_rcv.media is not None):
                self.assertEqual(media_rcv.media.path, 'PATH')
                self.assertEqual(media_rcv.media.kind, 'KIND')
                self.assertEqual(media_rcv.media.info, 'INFO')
                self.assertEqual(media_rcv.media.owning_process, Process.CAMERA)
                media_rcv.let_media_go()


@make_plugin('TestCam', Process.CAMERA)
class TestCam(PiCameraProcessBase):
    def __init__(self):
        super(TestCam, self).__init__()
        self._num_writes = 0
        self._num_flushes = 0
        self._num_analysis = 0

    @pyro_expose
    def get_picamera_root_plugin_id(self):
        return id(self.picamera_root_plugin)

    @pyro_expose
    @property
    def num_writes(self):
        return self._num_writes

    @pyro_expose
    @property
    def num_flushes(self):
        return self._num_flushes

    @pyro_expose
    @property
    def num_analysis(self):
        return self._num_analysis

    def write(self, data):
        self._num_writes += 1

    def flush(self):
        self._num_flushes += 1

    def analyze(self, array):
        self._num_analysis += 1


@make_plugin('InjectDemoData', Process.CAMERA)
class InjectDemoData(PluginProcessBase):
    def __init__(self):
        self._replay = None

    @pyro_expose
    def wait_for_completion(self):
        self._replay.has_stopped.wait()

    @pyro_expose
    def replay(self):
        self._replay.replay()

    def __enter__(self):
        events = load_demo_events()
        camera = find_plugin(PICAMERA_ROOT_PLUGIN_NAME).camera.camera
        self._replay = PiCameraReplay(events, camera)
        self._replay.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._replay.__exit__(exc_type, exc_val, exc_tb)
        self._replay = None


class TestPicameraPlugin(unittest.TestCase):

    def test_simple(self):
        plugins = {PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin)}
        with ProcessesHost(plugins):
            pass

    def test_with_another_plugin(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            'TestCam': ProcessPack(camera=TestCam)
        }
        with ProcessesHost(plugins) as host:
            picamera_plugin = host.plugin_instances[PICAMERA_ROOT_PLUGIN_NAME].camera
            testcam_plugin = host.plugin_instances['TestCam'].camera
            # Test that they agree on who is who
            self.assertEqual(picamera_plugin.get_remote_id(), testcam_plugin.get_picamera_root_plugin_id())

    def test_with_demo_data(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            'TestCam': ProcessPack(camera=TestCam),
            'InjectDemoData': ProcessPack(camera=InjectDemoData)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            test_cam_plugin = host.plugin_instances['TestCam'].camera
            injector.wait_for_completion()
            self.assertGreater(test_cam_plugin.num_writes, 0)
            self.assertGreater(test_cam_plugin.num_flushes, 0)
            self.assertGreater(test_cam_plugin.num_analysis, 0)


class TestBufferedRecorder(unittest.TestCase):
    def test_simple(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin)
        }
        with ProcessesHost(plugins):
            pass

    def test_demo_data(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            buffered_recorder = host.plugin_instances[BUFFERED_RECORDER_PLUGIN_NAME].camera
            buffered_recorder.record(12345)
            injector.wait_for_completion()


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
