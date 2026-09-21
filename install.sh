#!/bin/bash
set -o pipefail

LIBRARY_NAME=$(grep -m 1 name pyproject.toml | awk -F" = " '{print substr($2,2,length($2)-2)}')
MODULE_NAME="grow"
CONFIG_FILE=config.txt
DATESTAMP=$(date "+%Y-%m-%d-%H-%M-%S")
CONFIG_BACKUP=false
APT_HAS_UPDATED=false
RESOURCES_TOP_DIR="$HOME/Pimoroni"
RESOURCES_DIR="$RESOURCES_TOP_DIR/$LIBRARY_NAME"
VENV_BASH_SNIPPET="$RESOURCES_DIR/auto_venv.sh"
VENV_DIR="$HOME/.virtualenvs/pimoroni"
WD=$(pwd)
NATIVE_GPIO_HELPER="$WD/scripts/install-native-gpio.sh"
BOOT_ROOT="${GROW_BOOT_ROOT:-}"
CONFIG_DIR=""
CONFIG_PATH=""
USAGE="./install.sh (--unstable)"
POSITIONAL_ARGS=()
FORCE=false
UNSTABLE=false
PYTHON="python"
SYSTEM_PYTHON="/usr/bin/python3"


user_check() {
	if [ "$(id -u)" -eq 0 ]; then
		printf "Script should not be run as root. Try './install.sh'\n"
		exit 1
	fi
}

confirm() {
	if $FORCE; then
		true
	else
		read -r -p "$1 [y/N] " response < /dev/tty
		if [[ $response =~ ^(yes|y|Y)$ ]]; then
			true
		else
			false
		fi
	fi
}

prompt() {
	read -r -p "$1 [y/N] " response < /dev/tty
	if [[ $response =~ ^(yes|y|Y)$ ]]; then
		true
	else
		false
	fi
}

success() {
	echo -e "$(tput setaf 2)$1$(tput sgr0)"
}

inform() {
	echo -e "$(tput setaf 6)$1$(tput sgr0)"
}

warning() {
	echo -e "$(tput setaf 1)$1$(tput sgr0)"
}

die() {
	warning "$1"
	exit 1
}

find_config() {
	local boot_dir="${BOOT_ROOT}/boot"
	if [ -f "$boot_dir/firmware/$CONFIG_FILE" ]; then
		CONFIG_DIR="$boot_dir/firmware"
	elif [ -f "$boot_dir/$CONFIG_FILE" ]; then
		CONFIG_DIR="$boot_dir"
	else
		die "Could not find $boot_dir/firmware/$CONFIG_FILE or $boot_dir/$CONFIG_FILE. This installer requires a Raspberry Pi boot configuration."
	fi
	CONFIG_PATH="$CONFIG_DIR/$CONFIG_FILE"
	inform "Using $CONFIG_PATH"
}

apt_pkg_install() {
	local package
	local -a packages=()
	for package in "$@"; do
		[[ -z "$package" ]] && continue
		printf "Checking for %s\n" "$package"
		if ! dpkg -L "$package" >/dev/null 2>&1; then
			packages+=("$package")
		fi
	done
	if ((${#packages[@]} == 0)); then
		return 0
	fi
	echo "Installing missing packages: ${packages[*]}"
	if [[ "$APT_HAS_UPDATED" != true ]]; then
		sudo apt-get update || return 1
		APT_HAS_UPDATED=true
	fi
	sudo apt-get install -y "${packages[@]}" || return 1
}

venv_bash_snippet() {
	if [ ! -f "$VENV_BASH_SNIPPET" ]; then
		cat << EOF > "$VENV_BASH_SNIPPET"
# Add \`source $RESOURCES_DIR/auto_venv.sh\` to your ~/.bashrc to activate
# the Pimoroni virtual environment automagically!
VENV_DIR="$VENV_DIR"
if [ ! -f \$VENV_DIR/bin/activate ]; then
  printf "Creating user Python environment in \$VENV_DIR, please wait...\n"
  mkdir -p \$VENV_DIR
	python3 -m venv \$VENV_DIR
fi
printf " ↓ ↓ ↓ ↓   Hello, we've activated a Python venv for you. To exit, type \"deactivate\".\n"
source \$VENV_DIR/bin/activate
EOF
	fi
}

venv_check() {
	PYTHON_BIN=$(command -v "$PYTHON" || true)
	if [[ "${VIRTUAL_ENV:-}" != "$VENV_DIR" ]] || [[ "$PYTHON_BIN" != "$VENV_DIR/bin/"* ]]; then
		printf "This script should be run in a virtual Python environment.\n"
		if confirm "Would you like us to create one for you?"; then
			if [ ! -f "$VENV_DIR/bin/activate" ]; then
				inform "Creating virtual Python environment in $VENV_DIR, please wait...\n"
				mkdir -p "$VENV_DIR" || die "Could not create $VENV_DIR"
				if ! "$SYSTEM_PYTHON" -m venv "$VENV_DIR"; then
					inform "python3-venv is unavailable; bootstrapping it with apt..."
					apt_pkg_install python3-venv || die "Could not install python3-venv"
					"$SYSTEM_PYTHON" -m venv "$VENV_DIR" || die "Could not create $VENV_DIR"
				fi
				venv_bash_snippet
			else
				inform "Found existing virtual Python environment in $VENV_DIR\n"
			fi
			inform "Activating virtual Python environment in $VENV_DIR..."
			inform "source $VENV_DIR/bin/activate\n"
		else
			exit 1
		fi
	fi
	if grep -Eiq '^include-system-site-packages[[:space:]]*=[[:space:]]*true[[:space:]]*$' "$VENV_DIR/pyvenv.cfg" 2>/dev/null; then
		die "The interactive venv includes system site packages. Remove $VENV_DIR and rerun this installer for a clean environment."
	fi
	if "$VENV_DIR/bin/python" -m pip show RPi.GPIO >/dev/null 2>&1; then
		die "The interactive venv contains conflicting RPi.GPIO. Remove $VENV_DIR and rerun this installer."
	fi
	source "$VENV_DIR/bin/activate"
	PYTHON="$VENV_DIR/bin/python"
}

function do_config_backup {
	if [[ "$CONFIG_BACKUP" != true ]]; then
		CONFIG_BACKUP=true
		FILENAME="config.preinstall-$LIBRARY_NAME-$DATESTAMP.txt"
		inform "Backing up $CONFIG_PATH to $CONFIG_DIR/$FILENAME\n"
		sudo cp "$CONFIG_PATH" "$CONFIG_DIR/$FILENAME" || die "Could not back up $CONFIG_PATH"
		mkdir -p "$RESOURCES_TOP_DIR/config-backups/" || die "Could not create the config backup directory"
		cp "$CONFIG_PATH" "$RESOURCES_TOP_DIR/config-backups/$FILENAME" || die "Could not copy the config backup"
		if [ -f "$UNINSTALLER" ]; then
			printf 'sudo cp %q %q\n' "$RESOURCES_TOP_DIR/config-backups/$FILENAME" "$CONFIG_PATH" >> "$UNINSTALLER"
		fi
	fi
}

function pip_pkg_install {
	PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring $PYTHON -m pip install --upgrade "$@"
}

update_boot_config() {
	local config_line
	for config_line in "${CONFIG_TXT[@]}"; do
		[[ -n "$config_line" ]] && do_config_backup
	done

	if sudo "$SYSTEM_PYTHON" - "$CONFIG_PATH" "${CONFIG_TXT[@]}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
required = sys.argv[2:]
lines = path.read_text(encoding="utf-8").splitlines()

all_starts = [i for i, line in enumerate(lines) if line.strip().lower() == "[all]"]
all_start = all_starts[-1] if all_starts else None
if all_start is None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append("[all]")
    all_start = len(lines) - 1

all_end = next((i for i in range(all_start + 1, len(lines)) if lines[i].strip().startswith("[") and lines[i].strip().endswith("]")), len(lines))
if all_end < len(lines):
    lines.extend(["", "[all]"])
    all_start = len(lines) - 1
    all_end = len(lines)
def directive_identity(line):
    value = line.split("#", 1)[0].strip()
    if value.startswith("dtparam=i2c_arm="):
        return "dtparam=i2c_arm"
    if value.startswith("dtparam=spi="):
        return "dtparam=spi"
    if value == "dtoverlay=spi0-cs" or value.startswith("dtoverlay=spi0-cs,"):
        return "dtoverlay=spi0-cs"
    return value

required_identities = {directive_identity(config_line) for config_line in required}
for index in range(all_end - 1, all_start, -1):
    if directive_identity(lines[index]) in required_identities:
        lines.pop(index)
        all_end -= 1
for config_line in required:
    lines.insert(all_end, config_line)
    all_end += 1

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
	then
		return 0
	fi
	return 1
}

while [[ $# -gt 0 ]]; do
	K="$1"
	case $K in
	-u|--unstable)
		UNSTABLE=true
		shift
		;;
	-f|--force)
		FORCE=true
		shift
		;;
	-p|--python)
		PYTHON=$2
		shift
		shift
		;;
	*)
		if [[ $1 == -* ]]; then
			printf "Unrecognised option: %s\n" "$1";
			printf "Usage: %s\n" "$USAGE";
			exit 1
		fi
		POSITIONAL_ARGS+=("$1")
		shift
	esac
done

user_check
find_config
mkdir -p "$RESOURCES_DIR" || die "Could not initialise $RESOURCES_DIR"
venv_check

if ! command -v "$PYTHON" >/dev/null 2>&1; then
	printf "Python path %s not found!\n" "$PYTHON"
	exit 1
fi

PYTHON_VER=$($PYTHON --version)

printf "%s Python Library: Installer\n\n" $LIBRARY_NAME

inform "Checking Dependencies. Please wait..."

pip_pkg_install toml || die "Could not install the TOML parser"

CONFIG_VARS=`$PYTHON - <<EOF
import toml
config = toml.load("pyproject.toml")
p = dict(config['tool']['pimoroni'])
# Convert list config entries into bash arrays
for k, v in p.items():
    v = "'\n\t'".join(v)
    p[k] = f"('{v}')"
print("""
APT_PACKAGES={apt_packages}
SETUP_CMDS={commands}
CONFIG_TXT={configtxt}
""".format(**p))
EOF`

[[ $? -eq 0 ]] || die "Error parsing configuration"

eval "$CONFIG_VARS"

UNINSTALLER=$RESOURCES_DIR/uninstall.sh

cat << EOF > "$UNINSTALLER" || die "Could not write $UNINSTALLER"
printf "It's recommended you run these steps manually.\n"
printf "If you want to run the full script, open it in\n"
printf "an editor and remove 'exit 1' from below.\n"
exit 1
source $VIRTUAL_ENV/bin/activate
EOF

if $UNSTABLE; then
	warning "Installing unstable library from source.\n\n"
else
	printf "Installing stable library from pypi.\n\n"
fi

inform "Installing for $PYTHON_VER...\n"
apt_pkg_install "${APT_PACKAGES[@]}" || die "Could not install the system dependencies"
if [ ! -x "$NATIVE_GPIO_HELPER" ]; then
	die "Missing native GPIO helper at $NATIVE_GPIO_HELPER"
fi
sudo "$NATIVE_GPIO_HELPER" || die "Could not install native lgpio"
if $UNSTABLE; then
	pip_pkg_install . || die "Could not install the library from this checkout"
else
	pip_pkg_install "$LIBRARY_NAME" || die "Could not install $LIBRARY_NAME"
fi
success "Done!\n"
printf '%q -m pip uninstall -y %q\n' "$PYTHON" "$LIBRARY_NAME" >> "$UNINSTALLER"
if [ -f "requirements-examples.txt" ]; then
	pip_pkg_install -r requirements-examples.txt || die "Could not install example dependencies"
fi

cd "$WD" || exit 1

update_boot_config || die "Could not update $CONFIG_PATH"

if [ -d "examples" ]; then
	if confirm "Would you like to copy examples to $RESOURCES_DIR?"; then
		inform "Copying examples to $RESOURCES_DIR"
		cp -r examples/ "$RESOURCES_DIR" || die "Could not copy examples"
		printf 'rm -r %q\n' "$RESOURCES_DIR" >> "$UNINSTALLER"
		success "Done!"
	fi
fi

printf "\n"

if confirm "Would you like to generate documentation?"; then
	pip_pkg_install pdoc || die "Could not install pdoc"
	printf "Generating documentation.\n"
	"$PYTHON" -m pdoc "$MODULE_NAME" -o "$RESOURCES_DIR/docs" > /dev/null || die "Failed to generate documentation"
	inform "Documentation saved to $RESOURCES_DIR/docs"
	success "Done!"
fi

success "\nAll done!"
inform "If this is your first time installing you should reboot for hardware changes to take effect.\n"
inform "Find uninstall steps in $UNINSTALLER\n"
