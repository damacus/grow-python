import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install.sh"


def write_command(directory, name, body):
    command = directory / name
    command.write_text(f"#!/bin/bash\n{body}\n")
    command.chmod(0o755)
    return command


def test_installer_rejects_missing_boot_config_before_creating_resources(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_command(fake_bin, "id", 'printf "1000\\n"')

    environment = os.environ.copy()
    environment.update(
        {
            "GROW_BOOT_ROOT": str(tmp_path),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "TERM": "dumb",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(INSTALLER)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "requires a Raspberry Pi boot configuration" in result.stdout
    assert not (tmp_path / "home" / "Pimoroni").exists()


def test_mocked_install_updates_final_all_section_without_host_commands(tmp_path):
    boot_config = tmp_path / "boot" / "firmware" / "config.txt"
    boot_config.parent.mkdir(parents=True)
    boot_config.write_text(
        "[pi4]\nunrelated=keep\n[all]\n"
        "dtparam=spi=off\n"
        "dtparam=i2c_arm=off\n"
        "dtoverlay=spi0-cs,cs0_pin=8\n"
        "dtoverlay=spi0-cs-custom\n"
    )

    home = tmp_path / "home"
    venv_bin = home / ".virtualenvs" / "pimoroni" / "bin"
    venv_bin.mkdir(parents=True)
    venv_dir = venv_bin.parent
    (venv_bin / "activate").write_text(
        f'VIRTUAL_ENV="{venv_dir}"\nexport VIRTUAL_ENV\nPATH="$VIRTUAL_ENV/bin:$PATH"\nexport PATH\n'
    )
    write_command(
        venv_bin,
        "python",
        """
if [[ "$1" == "-m" && "$2" == "pip" && "$3" == "show" ]]; then
    exit 1
fi
if [[ "$1" == "--version" ]]; then
    printf 'Python 3.13.0\\n'
    exit 0
fi
if [[ "$1" == "-" ]]; then
    cat >/dev/null
    printf "APT_PACKAGES=()\\nSETUP_CMDS=()\\nCONFIG_TXT=('dtparam=i2c_arm=on' 'dtparam=spi=on' 'dtoverlay=spi0-cs,cs0_pin=14')\\n"
fi
exit 0
""",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_command(fake_bin, "id", 'printf "1000\\n"')
    write_command(fake_bin, "dpkg", "exit 0")
    write_command(fake_bin, "apt-get", f'touch "{tmp_path / "apt-was-called"}"; exit 0')
    write_command(
        fake_bin,
        "sudo",
        """
if [[ "$1" == */scripts/install-native-gpio.sh ]]; then
    exit 0
fi
exec "$@"
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "GROW_BOOT_ROOT": str(tmp_path),
            "HOME": str(home),
            "PATH": f"{venv_bin}:{fake_bin}:{environment['PATH']}",
            "TERM": "dumb",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(INSTALLER), "--unstable", "--force"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    updated = boot_config.read_text()
    assert "dtparam=i2c_arm=on\ndtparam=spi=on\n" in updated
    assert updated.rstrip().endswith("dtoverlay=spi0-cs,cs0_pin=14")
    assert "dtparam=spi=off" not in updated
    assert "dtparam=i2c_arm=off" not in updated
    assert "dtoverlay=spi0-cs,cs0_pin=8" not in updated
    assert "dtoverlay=spi0-cs-custom" in updated

    second = subprocess.run(
        ["/bin/bash", str(INSTALLER), "--unstable", "--force"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert boot_config.read_text() == updated
    assert not (tmp_path / "apt-was-called").exists()


@pytest.mark.parametrize(
    ("pyvenv_config", "pip_show_status", "message"),
    [
        (
            "include-system-site-packages = true\n",
            1,
            "includes system site packages",
        ),
        (
            "include-system-site-packages = false\n",
            0,
            "contains conflicting RPi.GPIO",
        ),
    ],
)
def test_active_target_venv_rejects_unclean_states(tmp_path, pyvenv_config, pip_show_status, message):
    boot_config = tmp_path / "boot" / "config.txt"
    boot_config.parent.mkdir(parents=True)
    boot_config.write_text("[all]\n")

    home = tmp_path / "home"
    venv_bin = home / ".virtualenvs" / "pimoroni" / "bin"
    venv_bin.mkdir(parents=True)
    venv_dir = venv_bin.parent
    (venv_dir / "pyvenv.cfg").write_text(pyvenv_config)
    (venv_bin / "activate").write_text(
        f'VIRTUAL_ENV="{venv_dir}"\nexport VIRTUAL_ENV\nPATH="$VIRTUAL_ENV/bin:$PATH"\nexport PATH\n'
    )
    write_command(
        venv_bin,
        "python",
        f"""
if [[ "$1" == "-m" && "$2" == "pip" && "$3" == "show" ]]; then
    exit {pip_show_status}
fi
exit 0
""",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_command(fake_bin, "id", 'printf "1000\\n"')

    environment = os.environ.copy()
    environment.update(
        {
            "GROW_BOOT_ROOT": str(tmp_path),
            "HOME": str(home),
            "PATH": f"{venv_bin}:{fake_bin}:{environment['PATH']}",
            "TERM": "dumb",
            "VIRTUAL_ENV": str(venv_dir),
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(INSTALLER), "--force"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert message in result.stdout
