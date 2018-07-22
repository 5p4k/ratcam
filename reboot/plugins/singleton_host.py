import os
import logging
import pickle
import Pyro4
import Pyro4.errors
from reboot.plugins.comm import create_sync_pair
from multiprocessing import Process


_log = logging.getLogger('singleton_host')


class SingletonHost:
    class SingletonServer:
        @Pyro4.expose
        def register(self, pickled_singleton):
            singleton_cls = pickle.loads(pickled_singleton)
            uri = self._daemon.register(singleton_cls(), singleton_cls.__name__)
            _log.debug('%s: serving at %s', singleton_cls.__name__, uri)
            return str(uri)

        @Pyro4.expose
        def close(self):
            _log.debug('SingletonServer: stopping')
            self._daemon.close()

        def __init__(self, daemon):
            self._daemon = daemon

    @staticmethod
    def _server(socket, transmit_sync):
        if os.path.exists(socket):
            os.remove(socket)
        daemon = Pyro4.Daemon(unixsocket=socket)
        uri = daemon.register(SingletonHost.SingletonServer(daemon), 'SingletonServer')
        _log.debug('SingletonServer: serving at %s', uri)
        transmit_sync.transmit(str(uri))
        daemon.requestLoop()
        _log.debug('SingletonServer: stopped serving at %s', uri)

    def __enter__(self):
        receiver, transmitter = create_sync_pair()
        self._process = Process(target=SingletonHost._server, args=(self._socket, transmitter))
        self._process.start()
        _log.debug('SingletonHost: waiting for server')
        uri = receiver.receive()
        self._instance = Pyro4.Proxy(uri)
        # Default serpent serializer does not trasmit a class
        self._instance._pyroSerializer = 'marshal'
        _log.debug('SingletonHost: obtained proxy at %s', uri)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._instance.close()
        except Pyro4.errors.ConnectionClosedError:
            # Is this even an error?
            pass

        _log.debug('SingletonHost signalled exit, waiting for server')
        self._process.join()
        _log.debug('SingletonHost server joined')
        self._instance = None
        self._process = None
        if os.path.exists(self._socket):
            os.remove(self._socket)

    def __call__(self, singleton_cls):
        if self._instance is None:
            raise RuntimeError('You must __enter__ into a SingletonHost.')
        # We cannot send a custom class except through Pickle, but we can't use pickle in Pyro because it's unsafe.
        # So we pickle the object and send it over marshal (because serpent does not serialize correctly bytes too)
        assert self._instance._pyroSerializer == 'marshal'
        return Pyro4.Proxy(self._instance.register(pickle.dumps(singleton_cls)))

    def __init__(self, socket):
        self._socket = socket
        self._process = None
        self._instance = None


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

    class Thingy:
        @Pyro4.expose
        def echo(self, msg):
            msg = 'Echoing %s' % repr(msg)
            print(msg)
            return msg

    Pyro4.config.SERIALIZER = 'marshal'

    with SingletonHost('temp.sock') as host:
        instance = host(Thingy)
        print('Received: "%s"' % instance.echo('<my message>'))
