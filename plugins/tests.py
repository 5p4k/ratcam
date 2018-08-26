import unittest
import os
from Pyro4 import expose as pyro_expose
from plugins.singleton_host import SingletonHost
from tempfile import TemporaryDirectory
from plugins.base import ProcessPack, Process, PluginProcessBase
from plugins.processes_host import ProcessesHost
from plugins.decorators import make_plugin, get_all_plugins


class TestSingletonHosts(unittest.TestCase):
    class SingletonProcessChecker:
        @pyro_expose
        def extract_pid(self):
            return os.getpid(), os.getppid()

    class MathTest:
        @staticmethod
        def static_do_math(a, b):
            return a * b + (b - a) * (a - b)

        @pyro_expose
        def do_math(self, a, b):
            return TestSingletonHosts.MathTest.static_do_math(a, b)

    def test_singleton_host(self):
        with TemporaryDirectory() as temp_dir:
            socket = os.path.join(temp_dir, 'test_singleton_host.sock')
            with SingletonHost(socket, 'test_singleton_host') as host:
                instance = host(TestSingletonHosts.SingletonProcessChecker)
                self.assertIsNotNone(instance)
                child_pid, parent_pid = instance.extract_pid()
                self.assertIsNotNone(child_pid)
                self.assertIsNotNone(parent_pid)
                current_pid = os.getpid()
                self.assertEqual(parent_pid, current_pid)
                self.assertNotEqual(child_pid, current_pid)

    def test_math_singleton_hosted(self):
        with TemporaryDirectory() as temp_dir:
            socket = os.path.join(temp_dir, 'test_math_singleton_hosted.sock')
            with SingletonHost(socket, 'test_math_singleton_hosted') as host:
                instance = host(TestSingletonHosts.MathTest)
                self.assertIsNotNone(instance)
                args = (1, 33)
                self.assertEqual(instance.do_math(*args), TestSingletonHosts.MathTest.static_do_math(*args))


class TestProcessPack(unittest.TestCase):
    def test_querying_with_process(self):
        pack = ProcessPack(*[process.value for process in Process])
        for process in Process:
            self.assertEqual(pack[process], process.value)
            self.assertEqual(pack[process.value], process.value)


class TestPluginProcess(unittest.TestCase):
    class TestProcess(PluginProcessBase):
        @pyro_expose
        def get_process(self):
            return self.process, os.getpid()

        @pyro_expose
        def get_sibling_pid_set(self):
            return set([instance.get_process()[1] for instance in self.plugin_instance_pack])

    def test_process_host(self):
        plugins = {
            'main': ProcessPack(TestPluginProcess.TestProcess,
                                TestPluginProcess.TestProcess,
                                TestPluginProcess.TestProcess)
        }
        with ProcessesHost(plugins) as processes:
            self.assertIn('main', processes.plugin_instances)
            instance_pack = processes.plugin_instances['main']
            for process in Process:
                self.assertIsNotNone(instance_pack[process])
                instance = instance_pack[process]
                if instance is not None:
                    process_in_instance, pid_in_instance = instance.get_process()
                    self.assertIsNotNone(process_in_instance)
                    self.assertIsNotNone(pid_in_instance)
                    self.assertNotEqual(pid_in_instance, os.getpid())
                    # Need to explicitly convert because the serialization engine may not preserve the Enum
                    self.assertEqual(Process(process_in_instance), process)

    def test_none_process_host(self):
        plugins = {
            'main': ProcessPack(None, None, None)
        }
        with ProcessesHost(plugins) as processes:
            instance_pack = processes.plugin_instances['main']
            for process in Process:
                self.assertIsNone(instance_pack[process])

    def test_intra_instance_talk(self):
        plugins = {
            'main': ProcessPack(TestPluginProcess.TestProcess,
                                TestPluginProcess.TestProcess,
                                TestPluginProcess.TestProcess)
        }
        with ProcessesHost(plugins) as processes:
            instance_pack = processes.plugin_instances['main']
            pid_sets = list([instance.get_sibling_pid_set() for instance in instance_pack])
            self.assertEqual(len(pid_sets), len(Process))
            if len(pid_sets) > 0:
                for pid_set in pid_sets[1:]:
                    self.assertEqual(pid_set, pid_sets[0])


class TestPluginDecorator(unittest.TestCase):
    @make_plugin('TestPluginDecorator', Process.MAIN)
    class DecoratedProcess(PluginProcessBase):
        @pyro_expose
        def get_two(self):
            return 2

    def test_process_host(self):
        with ProcessesHost(get_all_plugins()) as processes:
            self.assertIn('TestPluginDecorator', processes.plugin_instances)
            instance_pack = processes.plugin_instances['TestPluginDecorator']
            for process in Process:
                if process is Process.MAIN:
                    self.assertIsNotNone(instance_pack[process])
                    self.assertEqual(instance_pack[process].get_two(), 2)
                else:
                    self.assertIsNone(instance_pack[process])


if __name__ == '__main__':
    unittest.main()
