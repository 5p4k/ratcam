from plugins.base import Process, PluginProcessBase
from plugins.processes_host import find_plugin
from plugins.decorators import make_plugin
from collections import namedtuple
from math import isinf, isnan
from specialized.support.thread_host import CallbackThreadHost
from threading import Lock
from misc.logging import camel_to_snake, ensure_logging_setup
import logging
from misc.settings import SETTINGS
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway


STATUS_LED_PLUGIN_NAME = 'StatusLEDPlugin'
STATUS_LED_FPS = 25  # Do we really want this to be a setting too?
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(STATUS_LED_PLUGIN_NAME))


try:
    from gpiozero import RGBLED
except ImportError:
    _log.warning('Could not import RGBLED from gpiozero, running mock.')

    class RGBLED:
        def __init__(self, *_, **__):
            self._color = (0., 0., 0.)

        @property
        def color(self):
            return self._color

        @color.setter
        def color(self, v):
            assert isinstance(v, (tuple, list))
            assert len(v) == 3
            for comp in v:
                assert isinstance(comp, (int, float))
                assert 0 <= comp <= 1
            self._color = v


def infrange(n):
    if isinf(n):
        while True:
            yield float('inf')
    else:
        yield from range(int(n))


class BlinkingStatus(namedtuple('BlinkingStatusBase',
                                ['on_color', 'off_color', 'fade_in_time', 'fade_out_time', 'persist_on_time',
                                 'persist_off_time', 'n'])):
    @staticmethod
    def blend(col1, col2, frames):
        for i in range(frames):
            yield tuple([l + (r - l) * i / frames for l, r in zip(col1, col2)])

    def generate(self, initial_color=(0., 0., 0.), fps=25):
        if isnan(self.fade_in_time) or isinf(self.fade_in_time):
            raise ValueError('fade_in_time')
        if isnan(self.fade_out_time) or isinf(self.fade_out_time):
            raise ValueError('fade_out_time')
        if isnan(self.persist_on_time):
            raise ValueError('persist_on_time')
        if isnan(self.persist_off_time):
            raise ValueError('persist_off_time')
        # Initial transition
        initial_fade_in_frames = round(self.fade_in_time * fps)
        if initial_fade_in_frames > 0 and initial_color != self.on_color:
            yield from BlinkingStatus.blend(initial_color, self.on_color, initial_fade_in_frames)
        # Repeat the sequence
        fade_in_frames = max(1, round(self.fade_in_time * fps))
        fade_out_frames = max(1, round(self.fade_out_time * fps))
        persist_on_frames = float('inf') if isinf(self.persist_on_time) else \
            max(1, round(self.persist_on_time * fps))
        persist_off_frames = float('inf') if isinf(self.persist_off_time) else \
            max(1, round(self.persist_off_time * fps))

        def _generate_one_sequence(skip_fade_in=False):
            if not skip_fade_in:
                yield from BlinkingStatus.blend(self.off_color, self.on_color, fade_in_frames)
            for _ in infrange(persist_on_frames):
                yield self.on_color
            yield from BlinkingStatus.blend(self.on_color, self.off_color, fade_out_frames)
            for _ in infrange(persist_off_frames):
                yield self.off_color

        already_faded_in = True
        for _ in infrange(self.n):
            yield from _generate_one_sequence(skip_fade_in=already_faded_in)
            already_faded_in = False


class ContextualStatus:
    def __init__(self, blinking_status):
        self._blinking_status = blinking_status
        self._entered = False

    def cancel(self):
        if self._entered:
            self._entered = False
            plugin = find_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
            if plugin:
                plugin.cancel(self._blinking_status)

    def __enter__(self):
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cancel()


@make_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
class StatusLEDPlugin(PluginProcessBase):
    def __init__(self):
        self._active_statuses = []
        self._active_statuses_lock = Lock()
        self._active_statuses_iterators = []
        self._rgbled = None
        self._blink_thread = CallbackThreadHost('led_blinking_thread', action=self._winkwink_thread_callback)

    @staticmethod
    def get_bcm_pins_rgb():
        r = SETTINGS.status_led.get('bcm_pin_r', default=None, cast_to_type=int, ge=0, le=27, allow_none=True)
        g = SETTINGS.status_led.get('bcm_pin_g', default=None, cast_to_type=int, ge=0, le=27, allow_none=True)
        b = SETTINGS.status_led.get('bcm_pin_b', default=None, cast_to_type=int, ge=0, le=27, allow_none=True)
        if r is None and g is None and b is None:
            _log.warning('You did not specify a pin number for the status LED. It will not work.')
            return None
        if r is None or g is None or b is None or r == g or g == b or r == b:
            _log.error('You specified invalid values for the Status LED pins! It will not work.')
            return None
        return r, g, b

    def __enter__(self):
        pins = StatusLEDPlugin.get_bcm_pins_rgb()
        if pins is not None:
            self._rgbled = RGBLED(*pins)
            self._blink_thread.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Did we really start
        if self._rgbled:
            self._blink_thread.__exit__(exc_type, exc_val, exc_tb)
            self._rgbled = None

    def _winkwink_thread_callback(self):
        assert self._rgbled is not None
        while True:
            col = self._next_color()
            if col is None:
                break
            self._rgbled.color = col
            # The wait action for the stopping flags plays also the role of time.sleep
            if self._blink_thread.wait_stop(timeout=1. / STATUS_LED_FPS):
                break

    def _next_color(self):
        if self._rgbled is None:
            return None
        with self._active_statuses_lock:
            color = None
            to_delete = []
            # Advance all iterators but keep only the last value
            for i, it in enumerate(self._active_statuses_iterators):
                try:
                    color = next(it)
                except StopIteration:
                    to_delete.append(i)
            for i in sorted(to_delete, reverse=True):
                del self._active_statuses[i]
                del self._active_statuses_iterators[i]
            return color

    def _push(self, status):
        with self._active_statuses_lock:
            self._active_statuses.append(status)
            self._active_statuses_iterators.append(iter(status.generate(initial_color=self._rgbled.color,
                                                                        fps=STATUS_LED_FPS)))
            if len(self._active_statuses) == 1:
                self._blink_thread.wake()
        return status

    @pyro_expose
    @pyro_oneway
    def cancel(self, status):
        if self._rgbled is None:
            return
        with self._active_statuses_lock:
            if status not in self._active_statuses:
                return
            i = self._active_statuses.index(status)
            del self._active_statuses[i]
            del self._active_statuses_iterators[i]

    @pyro_expose
    def set(self, color, fade_in_time=0.5, persist_until_canceled=False):
        return self.push_status(on_color=color, off_color=color, fade_in_time=fade_in_time, fade_out_time=0.,
                                persist_on_time=0., persist_off_time=float('inf') if persist_until_canceled else 0.,
                                n=1)

    @pyro_expose
    def pulse(self, color, n=float('inf'), persist_time=0., frequency=1.):
        if frequency <= 0. or isnan(frequency) or isinf(frequency):
            raise ValueError('frequency')
        period = 1. / frequency
        return self.push_status(on_color=color, off_color=(0., 0., 0.), fade_in_time=0.5 * period,
                                fade_out_time=0.5 * period, persist_on_time=persist_time, persist_off_time=0., n=n)

    @pyro_expose
    def blink(self, color, n=float('inf'), duty_cycle=0.5, frequency=1.):
        if frequency <= 0. or isnan(frequency) or isinf(frequency):
            raise ValueError('frequency')
        if isnan(duty_cycle) or isinf(duty_cycle):
            raise ValueError('duty_cycle')
        duty_cycle = min(max(duty_cycle, 0.), 1.)
        period = 1. / frequency
        return self.push_status(on_color=color, off_color=(0., 0., 0.), fade_in_time=0., fade_out_time=0.,
                                persist_on_time=duty_cycle * period, persist_off_time=(1. - duty_cycle) * period, n=n)

    @pyro_expose
    def push_status(self, on_color, off_color=(0., 0., 0.), fade_in_time=0., fade_out_time=0.5, persist_on_time=0.,
                    persist_off_time=0., n=float('inf')):
        if fade_in_time < 0. or isinf(fade_in_time) or isnan(fade_in_time):
            raise ValueError('fade_in_time')
        if fade_out_time < 0. or isinf(fade_out_time) or isnan(fade_out_time):
            raise ValueError('fade_out_time')
        if persist_on_time < 0. or isnan(persist_on_time):
            raise ValueError('persist_on_time')
        if persist_off_time < 0. or isnan(persist_off_time):
            raise ValueError('persist_off_time')
        if not isinf(n) and not isinstance(n, int):
            raise TypeError('n')
        elif n == 0:
            raise ValueError('n')
        if not isinstance(on_color, (tuple, list)) or len(on_color) != 3:
            raise TypeError('on_color')
        if not isinstance(off_color, (tuple, list)) or len(off_color) != 3:
            raise TypeError('off_color')
        return ContextualStatus(self._push(BlinkingStatus(
            on_color=on_color, off_color=off_color, fade_in_time=fade_in_time, fade_out_time=fade_out_time,
            persist_on_time=persist_on_time, persist_off_time=persist_off_time, n=n
        )))


class Status:
    @staticmethod
    def set(color, fade_in_time=0.5, persist_until_canceled=False):
        plugin = find_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
        if plugin:
            return plugin.set(color, fade_in_time=fade_in_time, persist_until_canceled=persist_until_canceled)
        else:
            return ContextualStatus(None)

    @staticmethod
    def blink(color, n=float('inf'), duty_cycle=0.5, frequency=1.):
        plugin = find_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
        if plugin:
            return plugin.blink(color, n=n, duty_cycle=duty_cycle, frequency=frequency)
        else:
            return ContextualStatus(None)

    @staticmethod
    def pulse(color, n=float('inf'), persist_time=0., frequency=1.):
        plugin = find_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
        if plugin:
            return plugin.pulse(color, n=n, persist_time=persist_time, frequency=frequency)
        else:
            return ContextualStatus(None)

    @staticmethod
    def custom(on_color, off_color=(0., 0., 0.), fade_in_time=0., fade_out_time=0.5, persist_on_time=0.,
               persist_off_time=0., n=float('inf')):
        plugin = find_plugin(STATUS_LED_PLUGIN_NAME, Process.MAIN)
        if plugin:
            return plugin.push_status(on_color, off_color=off_color, fade_in_time=fade_in_time,
                                      fade_out_time=fade_out_time, persist_on_time=persist_on_time,
                                      persist_off_time=persist_off_time, n=n)
        else:
            return ContextualStatus(None)
