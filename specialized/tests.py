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
from safe_picamera import PiVideoFrameType
from specialized.plugin_still import StillPlugin, STILL_PLUGIN_NAME
from specialized.plugin_motion_detector import MotionDetectorResponder, MotionDetectorCameraPlugin, \
    MotionDetectorMainPlugin, MOTION_DETECTOR_PLUGIN_NAME


class RatcamUnitTestCase(unittest.TestCase):
    def retry_until_timeout(self, fn, timeout=1., sleep_step=0.001):  # pragma: no cover
        sleep_time = sleep_step
        start_time = time.time()
        while time.time() - start_time < timeout:
            if fn():
                return True
            time.sleep(sleep_time)
            sleep_time += sleep_step
        self.fail()


class RemoteMediaManager(MediaManagerPlugin):
    @pyro_expose
    def test_deliver_media(self, path, kind=None, info=None):
        self.deliver_media(path, kind, info)


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
        self._let_go_of_media.clear()


class TestMediaManager(RatcamUnitTestCase):
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
            ControlledMediaReceiver.plugin_name(): ProcessPack(main=ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(main=RemoteMediaManager)
        }
        with ProcessesHost(plugins) as phost:
            with tempfile.NamedTemporaryFile(delete=False) as media_file:
                path = media_file.name
            media_mgr = phost.plugin_instances[MEDIA_MANAGER_PLUGIN_NAME].main
            media_rcv = phost.plugin_instances[ControlledMediaReceiver.plugin_name()].main
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
            ControlledMediaReceiver.plugin_name(): ProcessPack(main=ControlledMediaReceiver),
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
            media_rcv = phost.plugin_instances[ControlledMediaReceiver.plugin_name()].main
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
    DEMO_DATA = load_demo_events()

    def __init__(self):
        self._replay = None

    @pyro_expose
    def wait_for_completion(self, timeout=None):
        return self._replay.has_stopped.wait(timeout=timeout)

    @pyro_expose
    def replay(self):
        self._replay.replay()

    def __enter__(self):
        camera = find_plugin(PICAMERA_ROOT_PLUGIN_NAME).camera.camera
        self._replay = PiCameraReplay(self.__class__.DEMO_DATA, camera)
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


class TestBufferedRecorder(RatcamUnitTestCase):
    def test_simple(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin)
        }
        with ProcessesHost(plugins):
            pass

    def retry_until_footage_age_changes(self, buffered_recorder, timeout=2., sleep_time=None):
        if sleep_time is None:
            sleep_time = max(0.01, 1. / InjectDemoData.DEMO_DATA['framerate'])

        def make_wait_fn(old_footage_age):
            return lambda: buffered_recorder.footage_age != old_footage_age
        self.retry_until_timeout(make_wait_fn(buffered_recorder.footage_age), timeout, sleep_time)

    def test_runs_with_demo_data(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            buffered_recorder = host.plugin_instances[BUFFERED_RECORDER_PLUGIN_NAME].camera
            buffered_recorder.record(12345)
            self.assertTrue(buffered_recorder.is_recording)
            injector.wait_for_completion()
            self.assertGreater(buffered_recorder.footage_age, 0)
            buffered_recorder.stop_and_discard()
            buffered_recorder.record(54321)
            injector.replay()
            # Wait until the buffer is cleared
            self.retry_until_footage_age_changes(buffered_recorder)
            # Wait until at least one frame is recorded
            self.retry_until_footage_age_changes(buffered_recorder)
            self.assertTrue(buffered_recorder.is_recording)
            self.assertGreater(buffered_recorder.footage_age, 0)
            buffered_recorder.stop_and_finalize()
            self.assertTrue(buffered_recorder.is_finalizing)
            injector.wait_for_completion()

    def test_dispatches_media(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData),
            ControlledMediaReceiver.plugin_name(): ProcessPack(camera=ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(camera=MediaManagerPlugin)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            buffered_recorder = host.plugin_instances[BUFFERED_RECORDER_PLUGIN_NAME].camera
            media_rcv = host.plugin_instances[ControlledMediaReceiver.plugin_name()].camera
            buffered_recorder.record(12345)
            injector.wait_for_completion()
            buffered_recorder.stop_and_discard()
            buffered_recorder.record(54321)
            injector.replay()
            injector.wait_for_completion()
            buffered_recorder.stop_and_finalize()
            self.assertTrue(os.path.isfile(media_rcv.media.path))
            self.assertEqual(media_rcv.media.kind, 'mp4')
            self.assertEqual(media_rcv.media.info, 54321)
            media_rcv.let_media_go()
            self.retry_until_timeout(lambda: not os.path.isfile(media_rcv.media.path))

    def test_rewinds(self):
        # Identify the max age of a split point
        max_sps_age = 0
        age = 0
        for evt in InjectDemoData.DEMO_DATA['events']:  # pragma: no cover
            if evt.frame is None:
                continue
            elif evt.frame.frame_type == PiVideoFrameType.sps_header:
                max_sps_age = max(max_sps_age, age)
                age = 0
            elif evt.frame.frame_type == PiVideoFrameType.key_frame or evt.frame.frame_type == PiVideoFrameType.frame:
                age += 1
        # We will play in a loop
        max_sps_age = max(age, max_sps_age)
        self.assertGreater(max_sps_age, 0)
        del age
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            BUFFERED_RECORDER_PLUGIN_NAME: ProcessPack(camera=BufferedRecorderPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData)
        }
        with ProcessesHost(plugins) as host:
            buffered_recorder = host.plugin_instances[BUFFERED_RECORDER_PLUGIN_NAME].camera
            # Patch the recorder to prevent frames to get too old
            buffered_recorder.sps_header_max_age = max_sps_age / 2
            buffered_recorder.buffer_max_age = max_sps_age / 2
            injector = host.plugin_instances['InjectDemoData'].camera
            max_buffer_age = 0
            max_footage_age = 0
            while not injector.wait_for_completion(0.1):
                max_buffer_age = max(buffered_recorder.buffer_age, max_buffer_age)
                max_footage_age = max(buffered_recorder.buffer_age, max_footage_age)
            injector.replay()
            while not injector.wait_for_completion(0.1):
                max_buffer_age = max(buffered_recorder.buffer_age, max_buffer_age)
                max_footage_age = max(buffered_recorder.buffer_age, max_footage_age)
            # On average we must not exceed by that much the max allowed buffer length
            self.assertLessEqual(max_buffer_age, buffered_recorder.total_age)
            self.assertLessEqual(max_footage_age, buffered_recorder.total_age)
            self.assertLessEqual(max_buffer_age, max_sps_age)
            self.assertLessEqual(max_footage_age, max_sps_age)


class TestStillPlugin(RatcamUnitTestCase):
    def test_simple(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            STILL_PLUGIN_NAME: ProcessPack(camera=StillPlugin)
        }
        with ProcessesHost(plugins):
            pass

    def test_runs_with_demo_data(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            STILL_PLUGIN_NAME: ProcessPack(camera=StillPlugin)
        }
        with ProcessesHost(plugins) as host:
            still = host.plugin_instances[STILL_PLUGIN_NAME].camera
            still.take_picture()

    def test_dispatches_media(self):
        plugins = {
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            STILL_PLUGIN_NAME: ProcessPack(camera=StillPlugin),
            ControlledMediaReceiver.plugin_name(): ProcessPack(camera=ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(camera=MediaManagerPlugin)
        }
        with ProcessesHost(plugins) as host:
            media_rcv = host.plugin_instances[ControlledMediaReceiver.plugin_name()].camera
            still = host.plugin_instances[STILL_PLUGIN_NAME].camera
            still.take_picture(123)
            self.retry_until_timeout(lambda: media_rcv.media is not None)
            self.assertTrue(os.path.isfile(media_rcv.media.path))
            self.assertEqual(media_rcv.media.kind, 'jpeg')
            self.assertEqual(media_rcv.media.info, 123)
            media_rcv.let_media_go()
            self.retry_until_timeout(lambda: not os.path.isfile(media_rcv.media.path))


class TestMotionDetectorPlugin(RatcamUnitTestCase):
    class TestMovementResponder(MotionDetectorResponder):
        def __init__(self):
            self._num_distinct_movements = 0
            self._num_wrong_changed_events = 0
            self._last_changed_event = None

        @classmethod
        def plugin_name(cls):  # pragma: no cover
            return 'InjectDemoData'

        @pyro_expose
        @property
        def num_distinct_movements(self):
            return self._num_distinct_movements

        @pyro_expose
        @property
        def num_wrong_changed_events(self):
            return self._num_wrong_changed_events

        def _motion_status_changed_internal(self, is_moving):
            if is_moving == self._last_changed_event:
                self._num_wrong_changed_events += 1
            self._last_changed_event = is_moving
            if is_moving:
                self._num_distinct_movements += 1

    def test_simple(self):
        plugins = {
            MOTION_DETECTOR_PLUGIN_NAME: ProcessPack(camera=MotionDetectorCameraPlugin, main=MotionDetectorMainPlugin),
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            injector.wait_for_completion()

    def test_motion_reported(self):
        plugins = {
            MOTION_DETECTOR_PLUGIN_NAME: ProcessPack(camera=MotionDetectorCameraPlugin, main=MotionDetectorMainPlugin),
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData, main=TestMotionDetectorPlugin.TestMovementResponder)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            responder = host.plugin_instances['InjectDemoData'].main
            injector.wait_for_completion()
            self.assertGreater(responder.num_distinct_movements, 0)
            self.assertEqual(responder.num_wrong_changed_events, 0)

    def test_take_motion_image(self):
        plugins = {
            MOTION_DETECTOR_PLUGIN_NAME: ProcessPack(camera=MotionDetectorCameraPlugin, main=MotionDetectorMainPlugin),
            PICAMERA_ROOT_PLUGIN_NAME: ProcessPack(camera=PiCameraRootPlugin),
            'InjectDemoData': ProcessPack(camera=InjectDemoData),
            ControlledMediaReceiver.plugin_name(): ProcessPack(camera=ControlledMediaReceiver),
            MEDIA_MANAGER_PLUGIN_NAME: ProcessPack(camera=MediaManagerPlugin)
        }
        with ProcessesHost(plugins) as host:
            injector = host.plugin_instances['InjectDemoData'].camera
            detector = host.plugin_instances[MOTION_DETECTOR_PLUGIN_NAME].camera
            media_rcv = host.plugin_instances[ControlledMediaReceiver.plugin_name()].camera
            injector.wait_for_completion()
            detector.take_motion_picture(123)
            self.retry_until_timeout(lambda: media_rcv.media is not None)
            self.assertTrue(os.path.isfile(media_rcv.media.path))
            self.assertEqual(media_rcv.media.kind, 'jpeg')
            self.assertEqual(media_rcv.media.info, 123)
            media_rcv.let_media_go()
            self.retry_until_timeout(lambda: not os.path.isfile(media_rcv.media.path))
