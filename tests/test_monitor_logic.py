"""Behavioural tests for the non-hardware parts of the example monitor."""

import builtins
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from PIL import Image
from test_display import load_monitor


class FakeSensor:
    def __init__(self, channel):
        self.channel = channel
        self.saturation = 0.5
        self.moisture = 12.5
        self.active = True
        self.history = []
        self.wet_point = None
        self.dry_point = None

    def set_wet_point(self, value):
        self.wet_point = value

    def set_dry_point(self, value):
        self.dry_point = value


class FakePump:
    def __init__(self, channel):
        self.channel = channel
        self.doses = []

    def dose(self, speed, duration, blocking=True):
        self.doses.append((speed, duration, blocking))
        return True


class FakePiezo:
    def __init__(self):
        self.beeps = []

    def beep(self, frequency, duration, blocking=True):
        self.beeps.append((frequency, duration, blocking))


@pytest.fixture
def monitor(monkeypatch):
    namespace = load_monitor(monkeypatch)
    runtime = namespace["Channel"].__init__.__globals__
    runtime["Moisture"] = FakeSensor
    runtime["Pump"] = FakePump
    runtime["Piezo"] = FakePiezo
    return namespace


def make_channel(monitor, **kwargs):
    return monitor["Channel"](1, 1, 1, **kwargs)


def test_channel_settings_and_watering_decision(monitor, monkeypatch):
    now = 100.0
    monkeypatch.setattr(monitor["time"], "time", lambda: now)
    channel = make_channel(monitor, title="Herbs", auto_water=True, watering_delay=10)

    assert channel.title == "Herbs"
    assert channel.sensor.wet_point == 0.7
    assert channel.sensor.dry_point == 26.7
    assert channel.indicator_color(1.0) == channel.colors[0]
    assert channel.indicator_color(0.0) == channel.colors[-1]
    assert channel.indicator_color(0.5) == (176, 237, 103)

    channel.last_dose = 0
    assert channel.water() is True
    assert channel.pump.doses == [(0.5, 0.2, False)]
    assert channel.water() is False

    channel.auto_water = False
    assert channel.water() is False
    channel.enabled = False
    channel.sensor.saturation = 0.1
    channel.update()
    assert channel.alarm is False

    channel.enabled = True
    channel.auto_water = True
    channel.last_dose = 0
    channel.update()
    assert channel.alarm is True
    assert len(channel.pump.doses) == 2

    channel.sensor.saturation = 0.9
    channel.update()
    assert channel.alarm is False

    channel.update_from_yml(
        {
            "pump_speed": 0.8,
            "pump_time": 0.4,
            "warn_level": 0.3,
            "water_level": 0.4,
            "watering_delay": 90,
            "auto_water": False,
            "enabled": False,
            "wet_point": 2.0,
            "dry_point": 24.0,
        }
    )
    channel.update_from_yml(None)
    assert channel.pump_speed == 0.8
    assert channel.pump_time == 0.4
    assert channel.warn_level == 0.3
    assert channel.water_level == 0.4
    assert channel.watering_delay == 90
    assert channel.auto_water is False
    assert channel.enabled is False
    assert channel.wet_point == 2.0
    assert channel.dry_point == 24.0
    assert "Channel: 1" in str(channel)


def test_alarm_trigger_sleep_and_beep_schedule(monitor, monkeypatch):
    now = 100.0
    monkeypatch.setattr(monitor["time"], "time", lambda: now)
    alarm = monitor["Alarm"](Image.new("RGBA", (160, 80)), interval=10, beep_frequency=880)

    alarm.update_from_yml({"alarm_enable": False, "alarm_interval": 4})
    alarm.update_from_yml(None)
    assert alarm.enabled is False
    assert alarm.interval == 4

    alarm.trigger()
    alarm.update(lights_out=True)
    assert alarm.piezo.beeps == []

    timer_calls = []

    class Timer:

        def __init__(self, delay, function, args=None, kwargs=None):
            timer_calls.append((delay, function, args, kwargs))

        def start(self):
            return None

    monkeypatch.setattr(monitor["threading"], "Timer", Timer)
    alarm.enabled = True
    alarm._time_last_beep = 0
    alarm.update()
    assert alarm.piezo.beeps == [(880, 0.1, False)]
    assert [call[0] for call in timer_calls] == [0.3, 0.6]
    for _, callback, args, kwargs in timer_calls:
        assert callback == alarm.piezo.beep
        assert args == [880, 0.1]
        assert kwargs == {"blocking": False}
    assert alarm._triggered is False

    alarm.trigger()
    alarm.sleep(duration=50)
    assert alarm.sleeping() is True
    alarm.update()
    assert alarm.sleeping() is True
    alarm.cancel_sleep()
    assert alarm.sleeping() is False
    alarm.sleep(duration=50)
    monkeypatch.setattr(monitor["time"], "time", lambda: 200.0)
    alarm.update()
    assert alarm.sleeping() is False

    alarm.icon = Mock()
    alarm.render((2, 3))
    assert alarm.icon.call_args.args[0] is monitor["icon_alarm"]
    alarm.sleep()
    alarm.render((2, 3))
    assert alarm.icon.call_args.args[0] is monitor["icon_snooze"]


def test_view_controller_navigates_views_and_subviews(monitor):
    first = Mock()
    second = Mock()
    third = Mock()
    first.button_a.return_value = False
    first.button_x.return_value = False
    second.button_x.return_value = True
    third.button_a.return_value = True
    controller = monitor["ViewController"]([(first, second), third])

    assert controller.home is True
    assert controller.view is first
    controller.update()
    controller.render()
    controller.button_b()
    first.update.assert_called_once_with()
    first.render.assert_called_once_with()
    first.button_b.assert_called_once_with()

    controller.button_x()
    assert controller.view is second
    assert controller.home is False
    controller.button_x()
    assert controller.view is second

    controller._current_subview = 0
    controller.button_a()
    assert controller.view is third
    controller.button_a()
    assert controller.view is third
    controller.button_y()
    third.button_y.assert_called_once_with()

    controller.prev_view()
    assert controller.view is first
    controller.next_view()
    assert controller.view is third
    controller.next_subview()
    assert controller.view is third


def test_config_loads_updates_and_saves_settings(monitor, monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text(
        "channel1:\n  enabled: true\n  pump_speed: 0.7\ngeneral:\n  alarm_enable: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(monitor["sys"], "argv", ["monitor.py", str(settings_file)])
    config = monitor["Config"]()
    config.load()

    assert config.get_channel(1) == {"enabled": True, "pump_speed": 0.7}
    assert config.get_channel(2) == {}
    assert config.get_general() == {"alarm_enable": False}

    channel = SimpleNamespace(
        enabled=True,
        warn_level=0.2,
        wet_point=1.0,
        dry_point=25.0,
        watering_delay=30,
        auto_water=True,
        pump_time=0.3,
        pump_speed=0.6,
        water_level=0.4,
    )
    config.set_channel(1, channel)
    config.set_general({"alarm_interval": 8})
    assert config.config["channel1"]["water_level"] == 0.4
    assert config.config["general"] == {"alarm_enable": False, "alarm_interval": 8}

    config.save()
    saved = settings_file.read_text(encoding="utf-8")
    assert "alarm_interval: 8" in saved

    open_spy = Mock(wraps=builtins.open)
    monkeypatch.setattr(builtins, "open", open_spy)
    config.save()
    open_spy.assert_not_called()

    config.config["general"]["alarm_interval"] = 10
    config.save()
    open_spy.assert_called_once_with(settings_file, "w")
    assert "alarm_interval: 10" in settings_file.read_text(encoding="utf-8")


def test_config_load_wraps_yaml_parser_errors(monitor, monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text("invalid", encoding="utf-8")
    monkeypatch.setattr(monitor["sys"], "argv", ["monitor.py"])

    def fail_load(_file):
        raise yaml.parser.ParserError(None, None, None, "bad settings")

    monkeypatch.setattr(monitor["yaml"], "safe_load", fail_load)
    with pytest.raises(yaml.parser.ParserError, match="Error parsing settings file"):
        monitor["Config"]().load(settings_file)
