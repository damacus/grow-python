"""Behavioural tests for the monitor's interactive display views."""

from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
from test_display import load_monitor


def channel(monitor, **overrides):
    """Build a hardware-free channel with the state the views consume."""
    sensor = SimpleNamespace(
        saturation=0.42,
        moisture=12.345,
        active=True,
        history=[0.1, 0.4, 0.8],
    )
    values = dict(
        channel=1,
        sensor=sensor,
        enabled=True,
        warn_level=0.5,
        alarm=True,
        water_level=0.6,
        auto_water=False,
        wet_point=0.7,
        dry_point=26.7,
        pump_time=0.2,
        pump_speed=0.5,
        watering_delay=60,
        indicator_color=lambda value: (10, 20, 30),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def image(monitor):
    return Image.new("RGBA", (monitor["DISPLAY_WIDTH"], monitor["DISPLAY_HEIGHT"]))


def test_edit_view_buttons_change_values_and_modes(monkeypatch):
    monitor = load_monitor(monkeypatch)
    target = SimpleNamespace(enabled=False, level=0.1, count=2)
    options = [
        {
            "title": "Enabled",
            "prop": "enabled",
            "mode": "bool",
            "format": lambda value: "Yes" if value else "No",
            "help": "Toggle this value",
        },
        {
            "title": "Level",
            "prop": "level",
            "mode": "float",
            "inc": 0.1,
            "min": 0.0,
            "max": 0.2,
            "round": 1,
            "format": lambda value: str(value),
            "help": "Set level",
            "object": target,
        },
        {
            "title": "Count",
            "prop": "count",
            "mode": "int",
            "inc": 1,
            "min": 0,
            "max": 3,
            "format": str,
            "help": "Set count",
            "object": target,
        },
    ]
    view = monitor["EditView"](image(monitor), options)
    view.channel = target

    assert view.button_x() is False
    assert view.button_y() is True
    assert view._change_mode is True
    assert view.button_y() is True
    assert target.enabled is True
    assert view.button_b() is True
    assert target.enabled is False
    assert view.button_x() is True

    assert view.button_b() is True
    assert view._current_option == 1
    view.button_y()
    view.button_y()
    assert target.level == 0.2
    view.button_b()
    assert target.level == 0.1
    view.button_x()

    view.button_b()
    view.button_y()
    view.button_y()
    assert target.count == 3
    view.button_b()
    assert target.count == 2


def test_edit_view_render_and_help_overlay(monkeypatch):
    monitor = load_monitor(monkeypatch)
    view = monitor["SettingsView"](
        image(monitor),
        [
            {
                "title": "Mode",
                "prop": "enabled",
                "mode": "bool",
                "format": lambda value: "Yes" if value else "No",
                "help": "Switch the channel on or off",
            }
        ],
    )
    view.channel = SimpleNamespace(enabled=True)
    view.render()
    assert view._image.getbbox() is not None
    assert view.button_a() is True
    current_option = view._current_option
    change_mode = view._change_mode
    view.render()
    assert view._help_mode is True
    assert view.button_b() is True
    assert view.button_y() is True
    assert view._current_option == current_option
    assert view._change_mode == change_mode
    assert view.button_a() is True
    assert view._help_mode is False


def test_channel_view_status_and_context_use_requested_metrics(monkeypatch):
    monitor = load_monitor(monkeypatch)
    view = monitor["ChannelView"](image(monitor), channel(monitor))
    text = Mock(wraps=view._draw.text)
    view._draw.text = text

    view.draw_status((1, 2))
    view.draw_context((3, 4))
    view.draw_context((5, 6), metric="sat")

    rendered = [call.args[1] for call in text.call_args_list]
    assert rendered == ["Sat: 42.00%", "Now: 12.35Hz", "Now: 42.00%"]


def test_detail_view_renders_history_alarm_and_inactive_channel(monkeypatch):
    monitor = load_monitor(monkeypatch)
    active = channel(monitor)
    view = monitor["DetailView"](image(monitor), active)
    view.icon = Mock()
    monkeypatch.setattr(monitor["time"], "time", lambda: 0)
    view.render()
    assert view._image.getpixel((60, 20))[:3] == (50, 50, 50)
    assert view._image.getpixel((127, 57))[:3] == (10, 20, 30)
    alarm_line = view._image.getpixel((10, 34))[:3]
    assert alarm_line == (191, 0, 0)
    assert alarm_line[1:] == (0, 0)
    assert any(call.args[0] is monitor["icon_alarm"] for call in view.icon.call_args_list)

    inactive = channel(monitor, enabled=False)
    inactive_view = monitor["DetailView"](image(monitor), inactive)
    inactive_view.icon = Mock()
    inactive_view.render()
    assert not any(
        call.args[0] is monitor["icon_alarm"]
        for call in inactive_view.icon.call_args_list
    )


def test_channel_edit_view_renders_context_for_sat_and_hz_options(monkeypatch):
    monitor = load_monitor(monkeypatch)
    view = monitor["ChannelEditView"](image(monitor), channel(monitor))
    view.draw_context = Mock()

    view.render()
    view.draw_context.assert_called_once_with((34, 6), "sat")

    view._current_option = 4
    view.render()
    view.draw_context.assert_called_with((34, 6), "hz")
    assert view.draw_context.call_count == 2

    view._current_option = 6
    view.render()
    assert view.draw_context.call_count == 2
