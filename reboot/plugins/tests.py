import unittest
import os
from Pyro4 import expose
from .singleton_host import SingletonHost
from tempfile import TemporaryDirectory


class TestSingletonHosts(unittest.TestCase):
    class SingletonProcessChecker:
        @expose
        def extract_pid(self):
            return os.getpid(), os.getppid()

    class MathTest:
        @staticmethod
        def static_do_math(a, b):
            return a * b + (b - a) * (a - b)

        @expose
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


if __name__ == '__main__':
    unittest.main()
