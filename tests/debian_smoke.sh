#!/usr/bin/env bash
set -euo pipefail

venv_dir="$(mktemp -d)"
python3 -m venv "$venv_dir"
trap 'rm -rf "$venv_dir"' EXIT

./scripts/install-native-gpio.sh

"$venv_dir/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r requirements-dev.txt
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r requirements-examples.txt
"$venv_dir/bin/python" -m pip install --disable-pip-version-check build mock pytest pytest-cov
"$venv_dir/bin/python" -m build --wheel --outdir dist
"$venv_dir/bin/python" -m pip install --disable-pip-version-check dist/*.whl
RPI_LGPIO_REVISION=c03114 "$venv_dir/bin/python" -c 'import RPi.GPIO; import st7735; import ltr559; from PIL import Image'
"$venv_dir/bin/python" -m pip check
"$venv_dir/bin/python" -m pytest -q tests
