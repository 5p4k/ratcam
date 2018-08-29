import os
import logging
import pickle
from Pyro4 import expose as pyro_expose, Daemon as PyroDaemon, Proxy as PyroProxy, oneway as pyro_oneway
import Pyro4
from plugins.comm import create_sync_pair
from multiprocessing import Process
from misc.logging import ensure_logging_setup
import traceback
from threading import Thread


ensure_logging_setup()
_log = logging.getLogger('singleton_host')


_log.info('Changing default Pyro4 serializer to pickle.')
Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')
Pyro4.config.SERIALIZER = 'pickle'


# The subprocesses have this many seconds to shut themselves off
_SHUTDOWN_TIMEOUT = 5


class SingletonHost:
    _LOCAL_SINGLETONS_BY_NAME = {}
    _LOCAL_SINGLETONS_BY_ID = {}

    class _SingletonServer:
        def _instantiate(self, singleton_cls):
            try:
                instance = singleton_cls()
            except Exception as e:  # pragma: no cover
                # This doesn't need to be covered by testing, we use it for debugging only
                _log.error('Unable to instantiate {}, error: {}, {}'.format(singleton_cls.__name__,
                                                                            e.__class__.__name__, str(e)))
                for line in traceback.format_exc().splitlines(keepends=False):
                    _log.debug(line)
                raise e
            id_name_pair = (id(instance), singleton_cls.__name__)
            self._hosted_singletons.append(id_name_pair)
            SingletonHost._LOCAL_SINGLETONS_BY_ID[id_name_pair[0]] = instance
            SingletonHost._LOCAL_SINGLETONS_BY_NAME[id_name_pair[1]] = instance
            # _log.info('Registered objects on {}: {}'.format(self._name, SingletonHost._LOCAL_SINGLETONS_BY_ID))
            return instance

        def _clear_instantiated_objs(self):
            for instance_id, instance_name in self._hosted_singletons:
                del SingletonHost._LOCAL_SINGLETONS_BY_NAME[instance_name]
                del SingletonHost._LOCAL_SINGLETONS_BY_ID[instance_id]
            del self._hosted_singletons[:]

        @pyro_expose
        def register_marshal(self, pickled_singleton):
            return self.register(pickle.loads(pickled_singleton))

        @pyro_expose
        def register(self, singleton_cls):
            uri = self._daemon.register(self._instantiate(singleton_cls), singleton_cls.__name__)
            _log.debug('%s: serving at %s', self._name, uri)
            return str(uri)

        @pyro_expose
        @pyro_oneway
        def close(self):
            _log.debug('%s: will stop.', self._name)
            self._clear_instantiated_objs()
            # Need to run on another thread, or it will cause a ConnectionClosedError
            Thread(target=self._daemon.shutdown, name='shutdown_thread').start()

        def __init__(self, daemon, name=None):
            self._daemon = daemon
            self._name = self.__class__.__name__ if name is None else name
            self._hosted_singletons = []

        @staticmethod
        def server_main(socket, transmit_sync, name='SingletonServer'):
            if os.path.exists(socket):
                os.remove(socket)
            daemon = PyroDaemon(unixsocket=socket)
            uri = daemon.register(SingletonHost._SingletonServer(daemon, name=name), name)
            _log.debug('%s: serving at %s', name, uri)
            transmit_sync.transmit(str(uri))
            daemon.requestLoop()
            _log.debug('%s: stopped serving at %s', name, uri)

    @classmethod
    def local_singletons_by_name(cls):
        return cls._LOCAL_SINGLETONS_BY_NAME

    @classmethod
    def local_singletons_by_id(cls):
        return cls._LOCAL_SINGLETONS_BY_ID

    def __enter__(self):
        receiver, transmitter = create_sync_pair()
        self._process = Process(target=SingletonHost._SingletonServer.server_main,
                                args=(self._socket, transmitter, self._name + 'Server'),
                                name=self._name)
        self._process.start()
        _log.debug('%s: waiting for server', self._name)
        uri = receiver.receive()
        self._instance = PyroProxy(uri)
        # Default serpent serializer does not trasmit a class
        if self._instance._pyroSerializer != 'pickle':
            self._instance._pyroSerializer = 'marshal'
        _log.debug('%s: obtained proxy at %s', self._name, uri)
        return self

    def initiate_shutdown(self):
        if self._instance is not None:
            self._instance.close()
            _log.debug('%s: signalled exit', self._name)
            # On Linux, Pyro does not query the stopping flag unless we call something.
            self._instance = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.initiate_shutdown()
        _log.debug('%s: waiting %0.1f seconds for server to join.', self._name, _SHUTDOWN_TIMEOUT)
        self._process.join(_SHUTDOWN_TIMEOUT)
        if self._process.is_alive():  # pragma: no cover
            _log.warning('%s: server did not join, terminating.', self._name)
            self._process.terminate()
        else:
            _log.debug('%s: server joined', self._name)
        self._process = None
        if os.path.exists(self._socket):
            os.remove(self._socket)

    def __call__(self, singleton_cls):
        if self._instance is None:
            raise RuntimeError('You must __enter__ into a %s.' % self.__class__.__name__)
        # We cannot send a custom class except through Pickle, but we can't use pickle in Pyro because it's unsafe.
        # So we pickle the object and send it over marshal (because serpent does not serialize correctly bytes too)
        assert self._instance._pyroSerializer in ['marshal', 'pickle']
        if self._instance._pyroSerializer == 'marshal':
            return PyroProxy(self._instance.register_marshal(pickle.dumps(singleton_cls)))
        elif self._instance._pyroSerializer == 'pickle':
            return PyroProxy(self._instance.register(singleton_cls))

    def __init__(self, socket, name=None):
        self._socket = socket
        self._process = None
        self._instance = None
        self._name = self.__class__.__name__ if name is None else name
