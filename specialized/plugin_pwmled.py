from plugins.base import Process, PluginProcessBase
from plugins.decorators import make_plugin
from misc.logging import camel_to_snake, ensure_logging_setup
import logging
from misc.settings import SETTINGS
from gpiozero import PWMLED
from Pyro4 import expose as pyro_expose, oneway as pyro_oneway


PWMLED_PLUGIN_NAME = 'PWMLed'
ensure_logging_setup()
_log = logging.getLogger(camel_to_snake(PWMLED_PLUGIN_NAME))


@make_plugin(PWMLED_PLUGIN_NAME, Process.MAIN)
class PWMLedPlugin(PluginProcessBase):
    def __init__(self):
        self._bcm_pin = SETTINGS.pwmled.get('bcm_pin', default=None, cast_to_type=int, ge=0, le=27, allow_none=True)
        self._frequency = SETTINGS.pwmled.get('frequency', default=100, cast_to_type=int, ge=10, le=10000)
        self._pwmled = None
        self._rebuild_pwmled()

    def _rebuild_pwmled(self):
        old_value = 0.
        if self._pwmled is not None:
            old_value = self._pwmled.value
            self._pwmled.off()
            self._pwmled = None
        if self._bcm_pin is not None:
            _log.debug('Rebuilding PWM led on pin %d with frequency %d.', self._bcm_pin, self._frequency)
            self._pwmled = PWMLED(self.bcm_pin, frequency=self.frequency, initial_value=old_value)
        else:
            _log.debug('Disabled PWM led.')

    @pyro_expose
    @property
    def frequency(self):
        return self._frequency

    @pyro_expose
    @frequency.setter
    def frequency(self, value):
        value = min(max(int(value), 10), 10000)
        if value != self._frequency:
            self._frequency = value
            self._rebuild_pwmled()

    @pyro_expose
    @property
    def bcm_pin(self):
        return self._bcm_pin

    @pyro_expose
    @bcm_pin.setter
    def bcm_pin(self, value):
        value = min(max(int(value), 0), 27)
        if value != self._bcm_pin:
            self._bcm_pin = value
            self._rebuild_pwmled()

    @pyro_expose
    @property
    def is_lit(self):
        if self._pwmled is not None:
            return self._pwmled.is_lit
        return None

    @pyro_expose
    @property
    def value(self):
        return None if self._pwmled is None else self._pwmled.value

    @pyro_expose
    @value.setter
    def value(self, v):
        if self._pwmled is not None:
            _log.info('Setting PWM led on pin %d to value %s.', self.bcm_pin, str(v))
            try:
                self._pwmled.value = v
            except Exception as e:  # pragma: no cover
                _log.exception('Unable to set value to %s.', str(v))
                raise e

    @pyro_expose
    @pyro_oneway
    def on(self):
        if self._pwmled is not None:
            _log.info('Turning on PWM led on pin %d.' % self.bcm_pin)
            self.value = 1.

    @pyro_expose
    @pyro_oneway
    def off(self):
        if self._pwmled is not None:
            _log.info('Turning off PWM led on pin %d.' % self.bcm_pin)
            self.value = 0.

    @pyro_expose
    @pyro_oneway
    def toggle(self):
        if self._pwmled is not None:
            if self.is_lit:
                self.off()
            else:
                self.on()

