#!/bin/bash
set -Eeuo pipefail

# Shared contract: install the native lgpio library and header required by the
# rpi-lgpio Python compatibility package. The caller must run this as root.
UPSTREAM_REPOSITORY="https://github.com/joan2937/lg.git"
UPSTREAM_COMMIT="bcccd782eceedc5b278b3056ea81d5fbbb89c489"

if [[ "$(id -u)" -ne 0 ]]; then
	printf 'This helper must be run as root (for example: sudo %s).\n' "$0" >&2
	exit 1
fi

apt-get update
apt-get install -y build-essential python3-dev swig ca-certificates git python3-venv

if apt-cache show liblgpio-dev >/dev/null 2>&1; then
	apt-get install -y liblgpio-dev
	ldconfig
	exit 0
fi

source_dir=$(mktemp -d "${TMPDIR:-/tmp}/grow-lgpio.XXXXXX")
cleanup() {
	rm -rf "$source_dir"
}
trap cleanup EXIT

git clone "$UPSTREAM_REPOSITORY" "$source_dir/lg"
git -C "$source_dir/lg" checkout --detach "$UPSTREAM_COMMIT"
[[ "$(git -C "$source_dir/lg" rev-parse HEAD)" == "$UPSTREAM_COMMIT" ]]
make -C "$source_dir/lg" liblgpio.so

install -Dm755 "$source_dir/lg/liblgpio.so.1" /usr/local/lib/liblgpio.so.1
ln -sfn liblgpio.so.1 /usr/local/lib/liblgpio.so
install -Dm644 "$source_dir/lg/lgpio.h" /usr/local/include/lgpio.h
ldconfig
