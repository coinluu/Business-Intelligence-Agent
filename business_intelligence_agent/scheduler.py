from __future__ import annotations

import os
import platform
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
    if system != "Darwin":
        raise RuntimeError("Business Intelligence Agent supports macOS only")
    command = _uv_command(project)
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


def uninstall() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Business Intelligence Agent supports macOS only")
    target = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
    _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False)
    target.unlink(missing_ok=True)


def set_enabled(enabled: bool) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Business Intelligence Agent supports macOS only")
    action = "enable" if enabled else "disable"
    _run(["launchctl", action, f"gui/{os.getuid()}/{LABEL}"])


def status() -> dict[str, object]:
    system = platform.system()
    if system != "Darwin":
        return {"installed": False, "supported": False, "detail": "Business Intelligence Agent supports macOS only"}
    result = _run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], check=False)
    return {"installed": result.returncode == 0, "detail": result.stdout[-4000:]}
