"""Exercise the monitor's wiring and one display cycle without Pi hardware."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_display import load_monitor


class EndCycle(Exception):
    """Stop the otherwise perpetual monitor loop after one iteration."""


@pytest.mark.parametrize("dark", [False, True])
def test_main_wires_buttons_channels_and_display_for_one_cycle(monkeypatch, dark):
    monitor = load_monitor(monkeypatch)
    main = monitor["main"]
    runtime = main.__globals__
    monkeypatch.setattr(runtime["sys"], "argv", ["monitor.py"])

    displays = []
    callbacks = {}
    channels = []
    alarms = []
    controllers = []

    class FakeDisplay:
        def __init__(self, **options):
            self.options = options
            self.begin = Mock()
            self.sleep = Mock()
            self.wake = Mock()
            self.display = Mock()
            displays.append(self)

    class FakeChannel:
        def __init__(self, display_channel, sensor_channel, pump_channel):
            self.channel = display_channel
            self.sensor_channel = sensor_channel
            self.pump_channel = pump_channel
            self.alarm = display_channel == 2
            self.settings = None
            self.updates = 0
            channels.append(self)

        def update_from_yml(self, settings):
            self.settings = settings

        def update(self):
            self.updates += 1

        def __str__(self):
            return f"Channel {self.channel}"

    class FakeAlarm:
        def __init__(self, image):
            self.enabled = True
            self.interval = 10.0
            self.triggers = 0
            self.updates = []
            self.sleeps = 0
            self.awake = True
            alarms.append(self)

        def update_from_yml(self, settings):
            self.settings = settings

        def update(self, lights_out):
            self.updates.append(lights_out)

        def trigger(self):
            self.triggers += 1

        def sleeping(self):
            return not self.awake

        def sleep(self):
            self.sleeps += 1
            self.awake = False

        def cancel_sleep(self):
            self.awake = True

    class FakeConfig:
        def __init__(self):
            self.loaded = False
            self.saved = 0
            self.channels = {}
            self.general = None
            runtime["test_config"] = self

        def load(self):
            self.loaded = True

        def get_channel(self, channel):
            return {"enabled": channel == 1}

        def get_general(self):
            return {"light_level_low": 10, "black_screen_when_light_low": True}

        def set_channel(self, channel, settings):
            self.channels[channel] = settings

        def set_general(self, settings):
            self.general = settings

        def save(self):
            self.saved += 1

    class FakeController:
        def __init__(self, views):
            self.views = views
            self.home = True
            self.updates = 0
            self.renders = 0
            self.buttons = []
            controllers.append(self)

        def update(self):
            self.updates += 1

        def render(self):
            self.renders += 1

        def button_a(self):
            self.buttons.append("A")

        def button_b(self):
            self.buttons.append("B")
            return False

        def button_x(self):
            self.buttons.append("X")

        def button_y(self):
            self.buttons.append("Y")

    gpio = SimpleNamespace(
        BCM=11,
        IN=0,
        PUD_UP=22,
        FALLING=2,
        setmode=Mock(),
        setwarnings=Mock(),
        setup=Mock(),
        add_event_detect=Mock(side_effect=lambda pin, edge, callback, bouncetime: callbacks.update({pin: callback})),
    )

    monkeypatch.setitem(runtime, "ST7735", SimpleNamespace(ST7735=FakeDisplay))
    monkeypatch.setitem(runtime, "ltr559", SimpleNamespace(LTR559=lambda: SimpleNamespace(get_lux=lambda: 0 if dark else 20)))
    monkeypatch.setitem(runtime, "GPIO", gpio)
    monkeypatch.setitem(runtime, "Channel", FakeChannel)
    monkeypatch.setitem(runtime, "Alarm", FakeAlarm)
    monkeypatch.setitem(runtime, "Config", FakeConfig)
    monkeypatch.setitem(runtime, "ViewController", FakeController)
    monkeypatch.setattr(runtime["time"], "sleep", Mock(side_effect=EndCycle))

    with pytest.raises(EndCycle):
        main()

    display = displays[0]
    alarm = alarms[0]
    controller = controllers[0]
    config = runtime["test_config"]
    assert display.options == {
        "port": 0,
        "cs": 1,
        "dc": 9,
        "backlight": 12,
        "rotation": 270,
        "spi_speed_hz": 80000000,
    }
    display.begin.assert_called_once_with()
    assert [(channel.channel, channel.sensor_channel, channel.pump_channel) for channel in channels] == [(1, 1, 1), (2, 2, 2), (3, 3, 3)]
    assert [channel.settings for channel in channels] == [{"enabled": True}, {"enabled": False}, {"enabled": False}]
    assert [channel.updates for channel in channels] == [1, 1, 1]
    assert alarm.triggers == 1
    assert alarm.updates == [dark]
    assert config.loaded and config.saved == 1
    assert sorted(config.channels) == [1, 2, 3]
    assert config.general == {"alarm_enable": True, "alarm_interval": 10.0}
    assert controller.updates == 1
    assert controller.renders == (0 if dark else 1)
    assert display.display.call_count == 1
    image = display.display.call_args.args[0]
    assert image.mode == "RGB"
    assert image.getpixel((50, 50)) == ((0, 0, 0) if dark else (255, 255, 255))
    assert display.sleep.call_count == int(dark)
    assert display.wake.call_count == int(not dark)
    gpio.setmode.assert_called_once_with(gpio.BCM)
    gpio.setwarnings.assert_called_once_with(False)
    gpio.setup.assert_called_once_with(runtime["BUTTONS"], gpio.IN, pull_up_down=gpio.PUD_UP)
    assert sorted(callbacks) == sorted(runtime["BUTTONS"])
    assert all(call.args[1] == gpio.FALLING and call.kwargs["bouncetime"] == 200 for call in gpio.add_event_detect.call_args_list)

    callbacks[5](5)
    callbacks[16](16)
    callbacks[24](24)
    callbacks[6](6)
    assert controller.buttons == ["A", "X", "Y", "B"]
    assert alarm.sleeps == 1
    callbacks[6](6)
    assert alarm.awake
