"""Regression tests for the monitor's Pillow display layout."""

import math
import runpy
import sys
import types
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image, ImageFont


def test_monitor_font_resource_is_loadable():
    font_path = files("font_roboto").joinpath("files/Roboto-Medium.ttf")
    assert font_path.is_file()
    assert ImageFont.truetype(str(font_path), 14).getbbox("Grow")


def load_monitor(monkeypatch):
    """Load monitor classes without starting the hardware display loop."""
    gpio = types.ModuleType("RPi.GPIO")
    gpio.BCM = 11
    gpio.IN = 0
    gpio.OUT = 1
    gpio.LOW = 0
    gpio.PUD_UP = 22
    gpio.FALLING = 2
    gpio.RISING = 3
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio

    ltr559 = types.ModuleType("ltr559")
    st7735 = types.ModuleType("st7735")
    font_roboto = types.ModuleType("font_roboto")

    monkeypatch.setitem(sys.modules, "RPi", rpi)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    monkeypatch.setitem(sys.modules, "ltr559", ltr559)
    monkeypatch.setitem(sys.modules, "st7735", st7735)
    monkeypatch.setitem(sys.modules, "font_roboto", font_roboto)

    class FontResources:
        def joinpath(self, _name):
            return Path("font_roboto/files/Roboto-Medium.ttf")

    monkeypatch.setattr(
        "importlib.resources.files", lambda _package: FontResources()
    )
    default_font = ImageFont.load_default()
    monkeypatch.setattr(
        "PIL.ImageFont.truetype",
        lambda *_args, **_kwargs: default_font,
    )

    for module_name in tuple(sys.modules):
        if module_name == "grow" or module_name.startswith("grow."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    monitor_path = Path(__file__).parents[1] / "examples" / "monitor.py"
    monkeypatch.chdir(monitor_path.parent)
    return runpy.run_path(str(monitor_path), run_name="monitor_test")


def test_view_layout_works_with_current_pillow(monkeypatch):
    monitor = load_monitor(monkeypatch)
    image = Image.new("RGBA", (monitor["DISPLAY_WIDTH"], monitor["DISPLAY_HEIGHT"]))
    view = monitor["View"](image)

    view.label("B", "OK", bgcolor=(255, 0, 0))
    assert image.getpixel((0, 61))[:3] == (255, 0, 0)
    assert image.getpixel((0, 60))[:3] == (0, 0, 0)
    view.clear()
    view.label("Y", "OK", bgcolor=(255, 0, 0))
    text_bbox = view._draw.textbbox((0, 0), "OK", font=view.font)
    label_x = monitor["DISPLAY_WIDTH"] - (text_bbox[2] - text_bbox[0] + 8)
    assert image.getpixel((label_x, 61))[:3] == (255, 0, 0)
    assert image.getpixel((133, 60))[:3] == (0, 0, 0)

    draw_text = Mock(wraps=view._draw.text)
    view._draw.text = draw_text
    bounds = view.text_in_rect(
        "one two three four",
        view.font,
        (3, 3, 63, 63),
    )

    rendered_lines = [call.args[1] for call in draw_text.call_args_list]
    assert len(rendered_lines) >= 2
    assert " ".join(rendered_lines) == "one two three four"
    assert [call.args[0][1] for call in draw_text.call_args_list] == sorted(
        call.args[0][1] for call in draw_text.call_args_list
    )
    assert bounds[0] >= 3
    assert bounds[1] >= 3
    assert bounds[2] <= 63
    assert bounds[3] <= 63
    assert image.getbbox() is not None


def test_channel_number_layout_is_rendered_in_main_and_detail_views(monkeypatch):
    monitor = load_monitor(monkeypatch)
    channel = SimpleNamespace(
        channel=1,
        sensor=SimpleNamespace(saturation=0.5, active=False, history=[]),
        enabled=False,
        warn_level=0.5,
        alarm=False,
        indicator_color=lambda value: (0, 0, 0),
    )
    image = Image.new("RGBA", (monitor["DISPLAY_WIDTH"], monitor["DISPLAY_HEIGHT"]))
    main_view = monitor["MainView"](image)
    main_view.icon = lambda *args: None
    main_text = Mock(wraps=main_view._draw.text)
    main_view._draw.text = main_text
    main_view.render_channel(channel)

    detail_image = Image.new("RGBA", (monitor["DISPLAY_WIDTH"], monitor["DISPLAY_HEIGHT"]))
    detail_view = monitor["DetailView"](detail_image, channel=channel)
    detail_view.icon = lambda *args: None
    detail_text = Mock(wraps=detail_view._draw.text)
    detail_view._draw.text = detail_text
    detail_view.render()

    font_bbox = main_view._draw.textbbox((0, 0), "1", font=main_view.font)
    text_width = font_bbox[2] - font_bbox[0]
    expected_position = (40 + math.ceil(8 - (text_width / 2.0)), 1)
    assert next(call for call in main_text.call_args_list if call.args[1] == "1").args[0] == expected_position
    assert next(call for call in detail_text.call_args_list if call.args[1] == "1").args[0] == expected_position
