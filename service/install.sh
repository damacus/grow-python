#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    printf 'Script must be run as root. Try: sudo %s\n' "$0" >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ASSET_DIR=/usr/share/grow-monitor
VENV_DIR=/opt/grow-monitor/venv
SERVICE_NAME=grow-monitor.service
NATIVE_GPIO_INSTALLER="${REPOSITORY_DIR}/scripts/install-native-gpio.sh"

if [[ ! -x "${NATIVE_GPIO_INSTALLER}" ]]; then
    printf 'Missing native GPIO prerequisite helper: %s\n' "${NATIVE_GPIO_INSTALLER}" >&2
    exit 1
fi
"${NATIVE_GPIO_INSTALLER}"

printf 'Installing Grow Monitor assets...\n'
install -d -m 0755 "${ASSET_DIR}/icons" /opt/grow-monitor
cp -a "${REPOSITORY_DIR}/examples/icons/." "${ASSET_DIR}/icons/"
install -m 0755 "${REPOSITORY_DIR}/examples/monitor.py" "${ASSET_DIR}/monitor.py"
ln -sfn "${ASSET_DIR}/monitor.py" /usr/bin/grow-monitor

# Keep settings made through the UI when the service is reinstalled.
if [[ ! -e /etc/default/grow ]]; then
    install -D -m 0644 "${REPOSITORY_DIR}/examples/settings.yml" /etc/default/grow
fi

printf 'Creating service virtual environment...\n'
if ! python3 -m venv "${VENV_DIR}"; then
    printf 'python3-venv is required. Install it with apt and run this script again.\n' >&2
    exit 1
fi
"${VENV_DIR}/bin/python" -m pip install --requirement "${REPOSITORY_DIR}/requirements-examples.txt"
"${VENV_DIR}/bin/python" -m pip install "${REPOSITORY_DIR}"
chown -R root:root "${VENV_DIR}"

printf 'Installing systemd service...\n'
install -m 0644 "${SCRIPT_DIR}/grow-monitor.service" "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    systemctl restart "${SERVICE_NAME}"
else
    systemctl start "${SERVICE_NAME}"
fi

printf '\nTo see Grow debug output, run: journalctl --no-pager --unit %s\n' "${SERVICE_NAME}"
