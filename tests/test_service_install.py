import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SERVICE = ROOT / "service" / "grow-monitor.service"
INSTALLER = ROOT / "service" / "install.sh"


def _write_command(path, body):
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o755)


def _sandbox(tmp_path):
    repo = tmp_path / "repo"
    (repo / "service").mkdir(parents=True)
    (repo / "examples" / "icons").mkdir(parents=True)
    for name, content in {"monitor.py": "#!/usr/bin/python3\n", "settings.yml": "default: true\n"}.items():
        (repo / "examples" / name).write_text(content)
    (repo / "examples" / "icons" / "icon.png").write_text("icon\n")
    (repo / "requirements-examples.txt").write_text("example\n")
    shutil.copy2(INSTALLER, repo / "service" / "install.sh")
    shutil.copy2(SERVICE, repo / "service" / "grow-monitor.service")

    paths = {
        "asset": tmp_path / "share" / "grow-monitor",
        "venv": tmp_path / "opt" / "grow-monitor" / "venv",
        "config": tmp_path / "etc" / "default" / "grow",
        "binary": tmp_path / "bin" / "grow-monitor",
        "unit": tmp_path / "etc" / "systemd" / "grow-monitor.service",
    }
    paths["binary"].parent.mkdir(parents=True)
    script = (repo / "service" / "install.sh").read_text()
    replacements = {
        "ASSET_DIR=/usr/share/grow-monitor": f"ASSET_DIR={paths['asset']}",
        "VENV_DIR=/opt/grow-monitor/venv": f"VENV_DIR={paths['venv']}",
        "install -d -m 0755 \"${ASSET_DIR}/icons\" /opt/grow-monitor": f"install -d -m 0755 \"${{ASSET_DIR}}/icons\" {paths['venv'].parent}",
        "install -D -m 0644 \"${REPOSITORY_DIR}/examples/settings.yml\" /etc/default/grow": f"install -D -m 0644 \"${{REPOSITORY_DIR}}/examples/settings.yml\" {paths['config']}",
        'ln -sfn "${ASSET_DIR}/monitor.py" /usr/bin/grow-monitor': f'ln -sfn "${{ASSET_DIR}}/monitor.py" {paths["binary"]}',
        'if [[ ! -e /etc/default/grow ]]; then': f'if [[ ! -e {paths["config"]} ]]; then',
        'install -m 0644 "${SCRIPT_DIR}/grow-monitor.service" "/etc/systemd/system/${SERVICE_NAME}"': f'install -m 0644 "${{SCRIPT_DIR}}/grow-monitor.service" {paths["unit"]}',
    }
    for old, new in replacements.items():
        script = script.replace(old, new)
    (repo / "service" / "install.sh").write_text(script)

    commands = tmp_path / "commands"
    commands.mkdir()
    _write_command(commands / "id", "print('0')")
    _write_command(commands / "install", """import os, shutil, sys
args = [arg for arg in sys.argv[1:] if not arg.startswith('-') and arg not in ('0755', '0644')]
if '-d' in sys.argv:
    for path in args: os.makedirs(path, exist_ok=True)
else:
    source, destination = args[-2:]
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
""")
    _write_command(commands / "chown", "raise SystemExit(0)")
    marker = tmp_path / "helper"
    _write_command(commands / "python3", f"""import pathlib, sys
if sys.argv[1:3] == ['-m', 'venv']:
    assert pathlib.Path({str(marker)!r}).exists()
    target = pathlib.Path(sys.argv[3]); (target / 'bin').mkdir(parents=True, exist_ok=True)
    (target / 'bin' / 'python').write_text('#!/bin/sh\\nexit 0\\n'); (target / 'bin' / 'python').chmod(0o755)
""")
    _write_command(commands / "systemctl", """import os, pathlib, sys
log = pathlib.Path(os.environ['SYSTEMCTL_LOG']); log.open('a').write(' '.join(sys.argv[1:]) + '\\n')
if sys.argv[1:2] == ['is-active']: raise SystemExit(0 if os.environ.get('ACTIVE') == '1' else 3)
""")
    helper = repo / "scripts" / "install-native-gpio.sh"
    helper.parent.mkdir()
    _write_command(helper, f"""import pathlib
marker = pathlib.Path({str(marker)!r})
if not marker.exists():
    assert not pathlib.Path({str(paths['asset'])!r}).exists()
    assert not pathlib.Path({str(paths['venv'])!r}).exists()
marker.write_text('helper-called')
""")
    helper.chmod(0o755)
    return repo, paths, commands, marker, tmp_path / "systemctl.log"


def _run(repo, commands, log, active="0", fail_python=False):
    python = commands / "python3"
    if fail_python:
        python.write_text("#!/bin/sh\nexit 42\n")
        python.chmod(0o755)
    env = os.environ | {"PATH": f"{commands}:{os.environ['PATH']}", "SYSTEMCTL_LOG": str(log), "ACTIVE": active}
    return subprocess.run(["bash", str(repo / "service" / "install.sh")], check=False, env=env, capture_output=True, text=True)


def test_installer_first_install_and_reinstall_preserve_settings(tmp_path):
    repo, paths, commands, helper, log = _sandbox(tmp_path)
    first = _run(repo, commands, log)
    assert first.returncode == 0, first.stderr
    assert helper.read_text() == "helper-called"
    paths["config"].write_text("user: setting\n")

    second = _run(repo, commands, log, active="1")
    assert second.returncode == 0, second.stderr
    assert paths["config"].read_text() == "user: setting\n"
    assert log.read_text().splitlines()[-4:] == ["daemon-reload", "enable grow-monitor.service", "is-active --quiet grow-monitor.service", "restart grow-monitor.service"]


def test_installer_starts_inactive_service_and_stops_on_dependency_failure(tmp_path):
    repo, _paths, commands, _helper, log = _sandbox(tmp_path)
    result = _run(repo, commands, log)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "daemon-reload",
        "enable grow-monitor.service",
        "is-active --quiet grow-monitor.service",
        "start grow-monitor.service",
    ]
    failed_repo, _, failed_commands, _, failed_log = _sandbox(tmp_path / "failed")
    failed = _run(failed_repo, failed_commands, failed_log, fail_python=True)
    assert failed.returncode != 0
    assert "python3-venv is required" in failed.stderr
    assert not failed_log.exists()


def test_installer_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(INSTALLER)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
