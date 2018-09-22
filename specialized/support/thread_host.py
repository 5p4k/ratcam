from threading import Thread, Event
from queue import Queue
import logging


class ThreadHost:
    def __init__(self, thread_name):
        self._thread_name = thread_name
        self._thread = None
        self._thread_wake = Event()
        self._thread_stop = Event()

    def __enter__(self):
        self._thread_wake.clear()
        self._thread_stop.clear()
        self._thread = Thread(target=self._thread_main, name=self._thread_name)
        self._thread.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._thread_stop.set()
        self._thread_wake.set()
        self._thread.join(1.)
        if self._thread.is_alive():  # pragma: no cover
            logging.getLogger(self._thread_name).warning('The thread %s did not join within 1s.', self._thread_name)
            self._thread.join()
            logging.getLogger(self._thread_name).info('The thread %s finally joined.', self._thread_name)

    def wake(self):
        self._thread_wake.set()

    def _action(self):
        pass

    def _thread_main(self):
        while not self._thread_stop.is_set():
            self._thread_wake.wait()
            self._thread_wake.clear()
            self._action()


class QueueThreadHost(ThreadHost):
    def __init__(self, thread_name):
        super(QueueThreadHost, self).__init__(thread_name)
        self._queue = Queue()

    def push_operation(self, o):
        self._queue.put_nowait(o)
        self.wake()

    def _queue_action(self, o):
        pass

    def _queue_cleared(self):
        pass

    def _action(self):
        while not self._queue.empty() and not self._thread_stop.is_set():
            self._queue_action(self._queue.get_nowait())
        if not self._thread_stop.is_set():
            self._queue_cleared()


class CallbackQueueThreadHost(QueueThreadHost):
    def __init__(self, thread_name, queue_action=None, queue_cleared=None):
        super(CallbackQueueThreadHost, self).__init__(thread_name)
        self._callback_queue_action = queue_action
        self._callback_queue_cleared = queue_cleared

    def _queue_cleared(self):
        if self._callback_queue_cleared is not None:
            self._callback_queue_cleared()

    def _queue_action(self, o):
        if self._callback_queue_action is not None:
            self._callback_queue_action(o)


class CallbackThreadHost(ThreadHost):
    def __init__(self, thread_name, action=None):
        super(CallbackThreadHost, self).__init__(thread_name)
        self._callback_action = action

    def _action(self):
        if self._callback_action is not None:
            self._callback_action()
