from unittest import mock

import pytest


def test_piezo_initialises_and_controls_pwm(GPIO, atexit):
    from grow import Piezo

    piezo = Piezo(gpio_pin=18)

    GPIO.setmode.assert_called_once_with(GPIO.BCM)
    GPIO.setwarnings.assert_called_once_with(False)
    GPIO.setup.assert_called_once_with(18, GPIO.OUT, initial=GPIO.LOW)
    GPIO.PWM.assert_called_once_with(18, 440)
    piezo.pwm.start.assert_called_once_with(0)
    atexit.register.assert_called_once_with(piezo._exit)

    piezo.frequency(880)
    piezo.start()
    piezo.start(frequency=660)
    piezo.stop()
    piezo._exit()

    piezo.pwm.ChangeFrequency.assert_has_calls([mock.call(880), mock.call(660)])
    piezo.pwm.ChangeDutyCycle.assert_has_calls([
        mock.call(1),
        mock.call(1),
        mock.call(0),
    ])
    piezo.pwm.stop.assert_called_once_with()


def test_piezo_blocking_beep_starts_sleeps_and_stops(GPIO, atexit):
    from grow import Piezo

    piezo = Piezo()
    with mock.patch("grow.time.sleep") as sleep:
        assert piezo.beep(frequency=523, timeout=0.25) is True

    piezo.pwm.ChangeFrequency.assert_called_once_with(523)
    sleep.assert_called_once_with(0.25)
    piezo.pwm.ChangeDutyCycle.assert_has_calls([mock.call(1), mock.call(0)])


def test_piezo_nonblocking_beep_rejects_busy_timer_unless_forced(GPIO, atexit):
    from grow import Piezo

    piezo = Piezo()
    first_timer = mock.Mock()
    first_timer.is_alive.side_effect = [True, True]
    forced_timer = mock.Mock()
    with mock.patch("grow.threading.Timer", side_effect=[first_timer, forced_timer]) as timer:
        assert piezo.beep(timeout=2, blocking=False) is True
        assert piezo.beep(timeout=2, blocking=False) is False
        assert piezo.beep(timeout=3, blocking=False, force=True) is True

    timer.assert_has_calls([mock.call(2, piezo.stop), mock.call(3, piezo.stop)])
    first_timer.start.assert_called_once_with()
    first_timer.cancel.assert_called_once_with()
    forced_timer.start.assert_called_once_with()


def test_moisture_pulses_update_reading_history_and_new_data(GPIO):
    from grow.moisture import Moisture

    sensor = Moisture(channel=2, wet_point=2, dry_point=10)
    sensor._time_last_reading = 8.0
    with mock.patch("grow.moisture.time.time", return_value=10.0):
        sensor._event_handler(sensor._gpio_pin)
        assert sensor.active is True

    assert sensor.new_data is True
    assert sensor.moisture == 0.5
    assert sensor.new_data is False
    assert sensor.history == [1.0]
    assert sensor._count == 0


def test_moisture_calibration_and_saturation_are_clamped(GPIO):
    from grow.moisture import Moisture

    sensor = Moisture(channel=1, wet_point=5, dry_point=25)
    sensor._reading = 15
    assert sensor.range == -20
    assert sensor.saturation == 0.5

    sensor._reading = 100
    assert sensor.saturation == 0.0
    sensor._reading = -100
    assert sensor.saturation == 1.0

    sensor.set_wet_point()
    assert sensor._wet_point == -100
    sensor.set_dry_point(42)
    assert sensor._dry_point == 42

    sensor._wet_point = 0
    sensor._dry_point = 100
    sensor._history = [100, 200, 0]
    assert sensor.history == [0.0, 0.0, 1.0]


def test_moisture_active_requires_recent_valid_reading(GPIO):
    from grow.moisture import Moisture

    sensor = Moisture()
    sensor._reading = 10
    sensor._last_pulse = 9.5
    with mock.patch("grow.moisture.time.time", return_value=10.0):
        assert sensor.active is True
    with mock.patch("grow.moisture.time.time", return_value=10.5):
        assert sensor.active is False

    sensor._last_pulse = 10.0
    sensor._reading = 28
    with mock.patch("grow.moisture.time.time", return_value=10.1):
        assert sensor.active is False


def test_moisture_reports_gpio_setup_errors(GPIO):
    from grow.moisture import Moisture

    GPIO.add_event_detect.side_effect = RuntimeError("edge detection failed")
    with pytest.raises(RuntimeError, match="edge detection failed"):
        Moisture(channel=1)

    GPIO.add_event_detect.side_effect = RuntimeError("BCM8 unavailable")
    with pytest.raises(RuntimeError, match="Unable to set up edge detection on BCM8"):
        Moisture(channel=2)
