from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from .files import atomic_write


LABEL = "io.github.business-intelligence-agent"


def _run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def _uv_command(project: Path) -> list[str]:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required before installing the scheduler")
    return [uv, "--directory", str(project), "run", "bia", "scheduled-tick"]


def install(project: Path) -> str:
    system = platform.system()
    command = _uv_command(project)
    if system == "Darwin":
        target = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
        arguments = "\n".join(f"      <string>{escape(value)}</string>" for value in command)
        content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array>
{arguments}
  </array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{escape(str(project / '.state/scheduler.stdout.log'))}</string>
  <key>StandardErrorPath</key><string>{escape(str(project / '.state/scheduler.stderr.log'))}</string>
</dict></plist>
'''
        atomic_write(target, content)
        _run(["plutil", "-lint", str(target)])
        _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False)
        _run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)])
        return str(target)

    if system == "Linux":
        unit_dir = Path.home() / ".config/systemd/user"
        service = unit_dir / f"{LABEL}.service"
        timer = unit_dir / f"{LABEL}.timer"
        exec_start = " ".join(shlex.quote(value) for value in command)
        atomic_write(service, f"[Unit]\nDescription=Business Intelligence Agent\n\n[Service]\nType=oneshot\nWorkingDirectory={project}\nExecStart={exec_start}\n")
        atomic_write(timer, "[Unit]\nDescription=Check Business Intelligence schedule\n\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=5min\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", f"{LABEL}.timer"])
        return str(timer)

    if system == "Windows":
        task_command = subprocess.list2cmdline(command)
        _run(["schtasks", "/Create", "/F", "/TN", LABEL, "/SC", "MINUTE", "/MO", "5", "/TR", task_command])
        return LABEL
    raise RuntimeError(f"Unsupported operating system: {system}")


def uninstall() -> None:
    system = platform.system()
    if system == "Darwin":
        target = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
        _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False)
        target.unlink(missing_ok=True)
    elif system == "Linux":
        _run(["systemctl", "--user", "disable", "--now", f"{LABEL}.timer"], check=False)
        unit_dir = Path.home() / ".config/systemd/user"
        (unit_dir / f"{LABEL}.service").unlink(missing_ok=True)
        (unit_dir / f"{LABEL}.timer").unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"], check=False)
    elif system == "Windows":
        _run(["schtasks", "/Delete", "/F", "/TN", LABEL], check=False)


def set_enabled(enabled: bool) -> None:
    system = platform.system()
    if system == "Darwin":
        action = "enable" if enabled else "disable"
        _run(["launchctl", action, f"gui/{os.getuid()}/{LABEL}"])
    elif system == "Linux":
        action = "start" if enabled else "stop"
        _run(["systemctl", "--user", action, f"{LABEL}.timer"])
    elif system == "Windows":
        action = "/Enable" if enabled else "/Disable"
        _run(["schtasks", "/Change", "/TN", LABEL, action])


def status() -> dict[str, object]:
    system = platform.system()
    if system == "Darwin":
        result = _run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], check=False)
    elif system == "Linux":
        result = _run(["systemctl", "--user", "status", f"{LABEL}.timer", "--no-pager"], check=False)
    elif system == "Windows":
        result = _run(["schtasks", "/Query", "/TN", LABEL, "/FO", "LIST"], check=False)
    else:
        return {"installed": False, "detail": f"unsupported OS: {system}"}
    return {"installed": result.returncode == 0, "detail": result.stdout[-4000:]}
