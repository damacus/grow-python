import atexit
import threading
import time

import RPi.GPIO as GPIO

PUMP_1_PIN = 17
PUMP_2_PIN = 27
PUMP_3_PIN = 22
PUMP_PWM_FREQ = 10000
PUMP_MAX_DUTY = 90


global_lock = threading.Lock()
_global_lock_state = threading.Lock()
_global_lock_owner = None


class Pump(object):
    """Grow pump driver."""

    def __init__(self, channel=1):
        """Create a new pump.

        Uses soft PWM to drive a Grow pump.

        :param channel: One of 1, 2 or 3.

        """

        self._gpio_pin = [PUMP_1_PIN, PUMP_2_PIN, PUMP_3_PIN][channel - 1]

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._gpio_pin, GPIO.OUT, initial=GPIO.LOW)
        self._pwm = GPIO.PWM(self._gpio_pin, PUMP_PWM_FREQ)
        self._pwm.start(0)

        self._state_lock = threading.RLock()
        self._timeout = None
        self._dose_generation = 0
        self._dose_active = False
        self._speed = 0.0
        self._hardware_stopped = False

        atexit.register(self._stop)

    def _stop(self):
        """Stop the PWM output and release this pump's global lock."""
        with self._state_lock:
            if self._hardware_stopped:
                return
            self.stop()
            self._pwm.stop()
            GPIO.setup(self._gpio_pin, GPIO.IN)
            self._hardware_stopped = True

    def _set_speed_locked(self, speed):
        """Set the speed while holding ``_state_lock``."""
        global _global_lock_owner

        if speed == 0:
            # Keep ownership until the hardware confirms that it stopped.
            self._pwm.ChangeDutyCycle(0)
            with _global_lock_state:
                if _global_lock_owner is self:
                    _global_lock_owner = None
                    global_lock.release()
            self._speed = 0.0
            return True

        acquired = False
        with _global_lock_state:
            if _global_lock_owner is not self:
                if not global_lock.acquire(blocking=False):
                    return False
                _global_lock_owner = self
                acquired = True

        try:
            self._pwm.ChangeDutyCycle(int(PUMP_MAX_DUTY * speed))
        except Exception:
            if acquired:
                with _global_lock_state:
                    _global_lock_owner = None
                    global_lock.release()
            raise
        self._speed = speed
        return True

    def set_speed(self, speed):
        """Set pump speed (PWM duty cycle)."""
        if speed > 1.0 or speed < 0:
            raise ValueError("Speed must be between 0 and 1")

        with self._state_lock:
            return self._set_speed_locked(speed)

    def get_speed(self):
        """Return Pump speed (PWM duty cycle)."""
        return self._speed

    def stop(self):
        """Stop the pump."""
        with self._state_lock:
            self._dose_generation += 1
            timeout = self._timeout
            self._timeout = None
            self._dose_active = False
            if timeout is not None:
                timeout.cancel()
            self._set_speed_locked(0)

    def _timer_expired(self, generation):
        """Stop only the dose represented by ``generation``."""
        with self._state_lock:
            if generation != self._dose_generation:
                return
            self._timeout = None
            self._dose_active = False
            self._dose_generation += 1
            self._set_speed_locked(0)

    def dose(self, speed, timeout=0.1, blocking=True, force=False):
        """Pulse the pump for timeout seconds.

        :param timeout: Timeout, in seconds, of the pump pulse
        :param blocking: If true, function will block until pump has stopped
        :param force: Applies only to non-blocking. If true, any previous dose will be replaced

        """

        if speed > 1.0 or speed < 0:
            raise ValueError("Speed must be between 0 and 1")

        with self._state_lock:
            if self._dose_active and (blocking or not force):
                return False

            if not self._set_speed_locked(speed):
                return False

            old_timeout = self._timeout
            self._dose_generation += 1
            generation = self._dose_generation
            self._timeout = None
            self._dose_active = True
            if old_timeout is not None:
                old_timeout.cancel()

            if not blocking:
                try:
                    timer = threading.Timer(
                        timeout, self._timer_expired, args=(generation,)
                    )
                    self._timeout = timer
                    timer.start()
                except Exception:
                    try:
                        self._stop_generation(generation)
                    except Exception:
                        raise
                    raise
                return True

        try:
            time.sleep(timeout)
            return True
        finally:
            self._stop_generation(generation)

    def _stop_generation(self, generation):
        """Stop a blocking dose unless a newer dose owns this pump."""
        with self._state_lock:
            if generation != self._dose_generation:
                return
            timeout = self._timeout
            self._timeout = None
            self._dose_active = False
            self._dose_generation += 1
            if timeout is not None:
                timeout.cancel()
            self._set_speed_locked(0)
