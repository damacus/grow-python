# Grow service

`service/install.sh` installs Grow Monitor as a system service on a Raspberry Pi
running Raspberry Pi OS or vanilla Debian 13. It installs the native GPIO and
Python build prerequisites before creating the service environment.

# Installing

```
sudo ./service/install.sh
```

The installer creates a root-owned virtual environment at
`/opt/grow-monitor/venv`, installs the example dependencies and this checkout
into it, and runs the service with that environment. It keeps an existing
`/etc/default/grow` file when the service is reinstalled. Icons and the monitor
script are installed under `/usr/share/grow-monitor`.

Complete the first-run hardware setup with the main installer before enabling
this service, for example `./install.sh --unstable` as the normal user when
installing from this checkout. Reboot after the main installer changes the boot
configuration, then run this service installer. The main installer configures
the Raspberry Pi and its user environment; this installer only creates the
separate service environment and systemd unit.

# Useful Commands

* View service status: `systemctl status grow-monitor`
* Stop service: `sudo systemctl stop grow-monitor`
* Start service: `sudo systemctl start grow-monitor`
* View full debug/error output: `journalctl --no-pager --unit grow-monitor`

## Configuring Grow

You can configure grow using the on-screen UI, or by editing the settings in `/etc/default/grow`.

[See the examples README.md](../examples/README.md#channel-settings) for an explanation of the options.
