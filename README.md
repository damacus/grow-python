# Grow HAT Mini

Designed as a tiny valet for your plants, Grow HAT mini will monitor the soil moiture for up to 3 plants, water them with tiny pumps, and show you their health on its small but informative screen. Learn more - https://shop.pimoroni.com/products/grow

[![Build Status](https://img.shields.io/github/actions/workflow/status/pimoroni/grow-python/test.yml?branch=main)](https://github.com/pimoroni/grow-python/actions/workflows/test.yml)
[![Coverage Status](https://coveralls.io/repos/github/pimoroni/grow-python/badge.svg?branch=master)](https://coveralls.io/github/pimoroni/grow-python?branch=master)
[![PyPi Package](https://img.shields.io/pypi/v/growhat.svg)](https://pypi.python.org/pypi/growhat)
[![Python Versions](https://img.shields.io/pypi/pyversions/growhat.svg)](https://pypi.python.org/pypi/growhat)

# Installing

The installer supports Raspberry Pi OS, including Trixie, and Debian 13
installed on Raspberry Pi hardware. It needs a Raspberry Pi boot configuration
at `/boot/firmware/config.txt` or `/boot/config.txt`; systems without either
file are rejected before any hardware changes are made.

## One-line (Installs from GitHub)

```
curl -sSL https://get.pimoroni.com/grow | bash
```

**Note** report issues with one-line installer here: https://github.com/pimoroni/get

## Install this checkout and configure dependencies:

* `git clone https://github.com/pimoroni/grow-python`
* `cd grow-python`
* `./install.sh --unstable`

Run the installer as your normal user. It creates a clean interactive
environment at `$HOME/.virtualenvs/pimoroni` and installs the example Python
dependencies. The service installer uses its separate root-owned environment at
`/opt/grow-monitor/venv`.

The installer enables I2C and SPI and adds the following lines under the
effective `[all]` section of the detected boot configuration:

```
dtparam=i2c_arm=on
dtparam=spi=on
dtoverlay=spi0-cs,cs0_pin=14
```

It installs `rpi-lgpio` as the GPIO provider. Do not install `RPi.GPIO` in the
same environment: both packages provide `RPi.GPIO`, and the clean venv avoids
that conflict. The native `lgpio` library is installed from the Raspberry Pi
package repository when available, or built from the pinned upstream source by
`scripts/install-native-gpio.sh`.

## Or... Install from PyPi and configure manually:

* Install dependencies:

```
python3 -m venv "$HOME/.virtualenvs/pimoroni"
source "$HOME/.virtualenvs/pimoroni/bin/activate"
python -m pip install growhat
python -m pip install -r requirements-examples.txt
```

* Run the commands inside the clean environment.

Manual installation does not perform the required boot configuration. Add the
three lines above under `[all]`, then reboot. It also needs the native `lgpio`
library and must not have `RPi.GPIO` installed in the same environment.


## Monitoring

You should read the following to get up and running with our monitoring script:

* [Using and configuring monitor.py](examples/README.md)
* [Setting up monitor.py as a service](service/README.md)

## Help & Support

* GPIO Pinout - https://pinout.xyz/pinout/grow_hat_mini
* Support forums - http://forums.pimoroni.com/c/support
* Discord - https://discord.gg/hr93ByC

# Changelog
0.0.2
-----

* Add mutually exclusive locking to pumps to avoid brownout running multiple pumps at once

0.0.1
-----

* Initial Release
