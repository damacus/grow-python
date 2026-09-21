import time
from unittest import mock

import pytest


class ControlledTimer:
    """Timer double whose callback runs only when the test asks it to."""

    instances = None
    constructor_error = None
    start_error = None

    def __init__(self, _timeout, callback, args=()):
        if self.__class__.constructor_error is not None:
            raise self.__class__.constructor_error
        self.callback = callback
        self.args = args
        self.cancelled = False
        self.started = False
        if self.__class__.instances is None:
            self.__class__.instances = []
        self.__class__.instances.append(self)

    def start(self):
        if self.__class__.start_error is not None:
            raise self.__class__.start_error
        self.started = True

    def cancel(self):
        self.cancelled = True

    def is_alive(self):
        return self.started and not self.cancelled

    def fire(self):
        self.callback(*self.args)


def test_pumps_actually_stop(GPIO, smbus):
    from grow.pump import Pump

    ch1 = Pump(channel=1)

    ch1.dose(speed=0.5, timeout=0.05, blocking=False)
    time.sleep(0.1)
    assert ch1.get_speed() == 0


def test_pumps_are_mutually_exclusive(GPIO, smbus):
    from grow.pump import Pump, global_lock

    ch1 = Pump(channel=1)
    ch2 = Pump(channel=2)
    ch3 = Pump(channel=3)

    ch1.dose(speed=0.5, timeout=1.0, blocking=False)

    assert global_lock.locked() is True

    assert ch2.dose(speed=0.5) is False
    assert ch2.dose(speed=0.5, blocking=False) is False

    assert ch3.dose(speed=0.5) is False
    assert ch3.dose(speed=0.5, blocking=False) is False


def test_pumps_run_sequentially(GPIO, smbus):
    from grow.pump import Pump, global_lock

    ch1 = Pump(channel=1)
    ch2 = Pump(channel=2)
    ch3 = Pump(channel=3)

    assert ch1.dose(speed=0.5, timeout=0.1, blocking=False) is True
    assert global_lock.locked() is True
    time.sleep(0.3)
    assert ch2.dose(speed=0.5, timeout=0.1, blocking=False) is True
    assert global_lock.locked() is True
    time.sleep(0.3)
    assert ch3.dose(speed=0.5, timeout=0.1, blocking=False) is True
    assert global_lock.locked() is True
    time.sleep(0.3)


def test_idle_stop_does_not_release_another_pumps_lock(GPIO, smbus):
    from grow.pump import Pump, global_lock

    ch1 = Pump(channel=1)
    ch2 = Pump(channel=2)

    assert ch1.dose(speed=0.5, timeout=1, blocking=False) is True
    ch2.stop()

    assert global_lock.locked() is True
    assert ch1.get_speed() == 0.5
    ch1.stop()
    assert global_lock.locked() is False


def test_idle_stop_is_safe_to_repeat(GPIO, smbus):
    from grow.pump import Pump

    pump = Pump(channel=1)
    pump.stop()
    pump.stop()

    assert pump.get_speed() == 0


def test_pwm_shutdown_uses_zero_argument_stop(GPIO, smbus):
    from grow.pump import Pump

    pwm = mock.Mock(spec=["start", "ChangeDutyCycle", "stop"])
    GPIO.PWM.return_value = pwm
    pump = Pump(channel=1)

    pump._stop()

    pwm.stop.assert_called_once_with()


def test_dose_validates_speed_before_starting_timer(GPIO, smbus, monkeypatch):
    from grow.pump import Pump

    ControlledTimer.instances = []
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    with pytest.raises(ValueError, match="between 0 and 1"):
        pump.dose(speed=1.1, timeout=10, blocking=False)

    assert ControlledTimer.instances == []


def test_timer_constructor_failure_cleans_up_dose(GPIO, smbus, monkeypatch):
    from grow.pump import Pump, global_lock

    ControlledTimer.instances = []
    ControlledTimer.constructor_error = RuntimeError("timer construction failed")
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    try:
        with pytest.raises(RuntimeError, match="timer construction failed"):
            pump.dose(speed=0.5, timeout=10, blocking=False)
    finally:
        ControlledTimer.constructor_error = None

    assert pump.get_speed() == 0
    assert global_lock.locked() is False


def test_timer_start_failure_cleans_up_dose(GPIO, smbus, monkeypatch):
    from grow.pump import Pump, global_lock

    ControlledTimer.instances = []
    ControlledTimer.start_error = RuntimeError("timer start failed")
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    try:
        with pytest.raises(RuntimeError, match="timer start failed"):
            pump.dose(speed=0.5, timeout=10, blocking=False)
    finally:
        ControlledTimer.start_error = None

    assert ControlledTimer.instances[0].cancelled is True
    assert pump.get_speed() == 0
    assert global_lock.locked() is False


def test_stop_keeps_lock_during_pwm_stop_callback(GPIO, smbus):
    from grow.pump import Pump, global_lock

    pwm1 = mock.Mock(spec=["start", "ChangeDutyCycle", "stop"])
    pwm2 = mock.Mock(spec=["start", "ChangeDutyCycle", "stop"])
    GPIO.PWM.side_effect = [pwm1, pwm2]
    ch1 = Pump(channel=1)
    ch2 = Pump(channel=2)
    assert ch1.set_speed(0.5) is True

    def stop_output(speed):
        if speed == 0:
            assert global_lock.locked() is True
            assert ch2.set_speed(0.5) is False

    pwm1.ChangeDutyCycle.side_effect = stop_output
    ch1.stop()

    assert global_lock.locked() is False
    assert ch2.set_speed(0.5) is True
    ch2.stop()
    pwm1.ChangeDutyCycle.side_effect = None


def test_repeated_speed_updates_keep_lock_ownership(GPIO, smbus):
    from grow.pump import Pump, global_lock

    pump = Pump(channel=1)

    assert pump.set_speed(0.25) is True
    assert pump.set_speed(0.75) is True
    assert pump.get_speed() == 0.75
    pump.stop()
    assert global_lock.locked() is False


def test_refused_competing_dose_keeps_existing_timer(GPIO, smbus, monkeypatch):
    from grow.pump import Pump

    ControlledTimer.instances = []
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    ch1 = Pump(channel=1)
    ch2 = Pump(channel=2)

    assert ch1.dose(speed=0.5, timeout=10, blocking=False) is True
    first_timer = ControlledTimer.instances[0]

    assert ch2.dose(speed=0.5, timeout=10, blocking=False) is False
    assert ch1.get_speed() == 0.5
    assert first_timer.cancelled is False

    first_timer.fire()
    assert ch1.get_speed() == 0


def test_stale_timer_cannot_stop_replaced_dose(GPIO, smbus, monkeypatch):
    from grow.pump import Pump

    ControlledTimer.instances = []
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    assert pump.dose(speed=0.25, timeout=10, blocking=False) is True
    first_timer = ControlledTimer.instances[0]
    assert pump.dose(speed=0.75, timeout=20, blocking=False, force=True) is True
    second_timer = ControlledTimer.instances[1]

    first_timer.fire()
    assert pump.get_speed() == 0.75
    assert second_timer.cancelled is False

    second_timer.fire()
    assert pump.get_speed() == 0


def test_force_false_does_not_replace_active_dose(GPIO, smbus, monkeypatch):
    from grow.pump import Pump

    ControlledTimer.instances = []
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    assert pump.dose(speed=0.5, timeout=10, blocking=False) is True
    first_timer = ControlledTimer.instances[0]
    assert pump.dose(speed=0.75, timeout=20, blocking=False) is False
    assert pump.get_speed() == 0.5
    assert first_timer.cancelled is False


def test_force_does_not_replace_active_dose_for_blocking_call(GPIO, smbus, monkeypatch):
    from grow.pump import Pump

    ControlledTimer.instances = []
    monkeypatch.setattr("grow.pump.threading.Timer", ControlledTimer)
    pump = Pump(channel=1)

    assert pump.dose(speed=0.5, timeout=10, blocking=False) is True
    first_timer = ControlledTimer.instances[0]
    assert pump.dose(speed=0.75, timeout=0, blocking=True, force=True) is False
    assert pump.get_speed() == 0.5
    assert first_timer.cancelled is False

    first_timer.fire()


def test_blocking_dose_cleans_up_when_sleep_fails(GPIO, smbus, monkeypatch):
    from grow.pump import Pump, global_lock

    pump = Pump(channel=1)
    monkeypatch.setattr("grow.pump.time.sleep", mock.Mock(side_effect=RuntimeError))

    try:
        pump.dose(speed=0.5, timeout=1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected sleep failure")

    assert pump.get_speed() == 0
    assert global_lock.locked() is False


def test_stop_keeps_lock_when_pwm_change_fails(GPIO, smbus):
    from grow.pump import Pump, global_lock

    pwm = mock.Mock(spec=["start", "ChangeDutyCycle", "stop"])
    GPIO.PWM.return_value = pwm
    pump = Pump(channel=1)
    assert pump.set_speed(0.5) is True

    pwm.ChangeDutyCycle.side_effect = RuntimeError("PWM failure")
    try:
        pump.stop()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected PWM failure")

    assert global_lock.locked() is True
    assert pump.get_speed() == 0.5

    pwm.ChangeDutyCycle.side_effect = None
    pump.stop()
    assert global_lock.locked() is False
