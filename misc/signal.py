import signal
from threading import Event


class GracefulSignal:
    def __init__(self, sig=signal.SIGINT):
        self._sig = sig
        self._old_handler = None
        self._evt = Event()

    def _handler(self, sig, frame):
        self._evt.set()

    def __enter__(self):
        self._old_handler = signal.getsignal(self._sig)
        signal.signal(self._sig, self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.signal(self._sig, self._old_handler)
        self._evt.clear()

    def wait(self):
        self._evt.wait()
