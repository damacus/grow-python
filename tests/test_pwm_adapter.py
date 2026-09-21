"""Hardware-free checks against the installed rpi-lgpio compatibility layer."""

import importlib
import sys
import types

import pytest


class RecordingLgpio(types.ModuleType):
    """Small lgpio double which records calls made by RPi.GPIO."""

    def __init__(self):
        super().__init__("lgpio")
        self.calls = []
        self.output_pins = set()

    def __getattr__(self, name):
        # rpi-lgpio has a few release-to-release helper calls. Returning a
        # callable here keeps this test focused on the PWM contract rather
        # than duplicating the adapter's whole lgpio surface.
        if name.startswith("gpio") or name.startswith("tx_"):
            def record(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                if name == "gpio_claim_output":
                    self.output_pins.add(args[1])
                elif name in {"gpio_claim_input", "gpio_free"}:
                    self.output_pins.discard(args[1])
                elif name == "gpio_get_mode":
                    # rpi-lgpio exposes its output mode as bit 0x200 and
                    # checks this before creating PWM.
                    return 0x200 if args[1] in self.output_pins else 0
                return 0

            return record
        if name.isupper():
            return 0
        raise AttributeError(name)


def test_pump_pwm_contract_through_rpi_lgpio(monkeypatch):
    """Exercise Pump through the real adapter without opening GPIO hardware."""
    try:
        adapter_spec = importlib.util.find_spec("RPi.GPIO")
    except (ImportError, ModuleNotFoundError, ValueError):
        pytest.skip("rpi-lgpio is not installed")
    if adapter_spec is None:
        pytest.skip("rpi-lgpio is not installed")

    # The CI container has no Raspberry Pi revision exposed by /proc. This
    # selects the same supported revision used by the Debian smoke check.
    monkeypatch.setenv("RPI_LGPIO_REVISION", "c03114")
    fake_lgpio = RecordingLgpio()
    monkeypatch.setitem(sys.modules, "lgpio", fake_lgpio)
    # Avoid a previously imported adapter retaining the native lgpio module.
    monkeypatch.delitem(sys.modules, "RPi.GPIO", raising=False)
    monkeypatch.delitem(sys.modules, "RPi", raising=False)
    monkeypatch.delitem(sys.modules, "grow.pump", raising=False)
    monkeypatch.delitem(sys.modules, "grow", raising=False)

    GPIO = importlib.import_module("RPi.GPIO")

    pump_module = importlib.import_module("grow.pump")
    PUMP_PWM_FREQ, Pump = pump_module.PUMP_PWM_FREQ, pump_module.Pump

    # Pump uses one process-wide lock, so each channel must release hardware
    # before the next channel can claim it.
    pumps = []
    for channel, speed in zip((1, 2, 3), (0.25, 0.5, 1.0)):
        pump = Pump(channel)
        pumps.append(pump)
        assert pump.set_speed(speed)
        pump._stop()

    assert [pump._gpio_pin for pump in pumps] == [17, 27, 22]

    pwm_calls = [call for call in fake_lgpio.calls if call[0] == "tx_pwm"]
    for pin, duty in zip((17, 27, 22), (22, 45, 90)):
        pin_calls = [args[2:] for _, args, _ in pwm_calls if args[1] == pin]
        assert pin_calls == [
            (PUMP_PWM_FREQ, 0),
            (PUMP_PWM_FREQ, duty),
            (PUMP_PWM_FREQ, 0),
            (0, 0),
        ]

    # Pump._stop must hand each pin back through the adapter's input cleanup
    # path after PWM.stop(). Adapter versions use gpio_claim_input or
    # gpio_free for that transition, so accept either implementation detail.
    cleanup_calls = [
        call for call in fake_lgpio.calls if call[0] in {"gpio_claim_input", "gpio_free"}
    ]
    assert all(any(pin in args for _, args, _ in cleanup_calls) for pin in (17, 27, 22))
    assert GPIO is sys.modules["RPi.GPIO"]
