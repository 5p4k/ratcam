import Pyro4
import os
from multiprocessing import Process, Event, Pipe


class Sync:
    def reset(self):
        self._uri = None
        self._ostream.recv()
        self._ready.clear()

    def wait_for_uri(self, timeout=None):
        if self._ready.wait(timeout=timeout):
            return self.uri
        return None

    @property
    def uri(self):
        if self._ready.is_set():
            if self._uri is None:
                self._uri = self._ostream.recv()
        return self._uri

    @uri.setter
    def uri(self, value):
        self._istream.send(value)
        self._ready.set()

    def __init__(self):
        self._ready = Event()
        self._uri = None
        self._ostream, self._istream = Pipe(False)


@Pyro4.expose
class Thingy:
    def message(self, arg):
        print('Message: {}'.format(arg))
        return 'Received and printed'


def server(sync):
    if os.path.exists('example_unix.sock'):
        os.remove('example_unix.sock')
    d = Pyro4.Daemon(unixsocket='example_unix.sock')
    uri = d.register(Thingy(), 'example.unixsock')
    print('Server running, uri={}'.format(uri))
    sync.uri = str(uri)
    d.requestLoop()


def client(sync):
    print('Client running, waiting for uri.')
    uri = sync.wait_for_uri()
    print('Obtained uri, {}'.format(repr(uri)))
    with Pyro4.Proxy(uri) as p:
        response = p.message('Hello there!')
    print('Response was: {}'.format(response))


def main():
    sync = Sync()
    p_server = Process(target=server, args=(sync,))
    p_client = Process(target=client, args=(sync,))
    p_server.start()
    p_client.start()
    p_server.join()
    p_client.join()


if __name__ == '__main__':
    main()
