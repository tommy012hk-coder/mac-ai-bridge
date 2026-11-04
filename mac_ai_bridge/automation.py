"""Keyboard-driven UI automation for supported Mac AI apps."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


MAX_PROMPT_LENGTH = 8_000
RESPONSE_TIMEOUT_SECONDS = 180
PROJECT_ROOT = Path(__file__).resolve().parent
NATIVE_HELPER = PROJECT_ROOT / "macos_ui.swift"


@dataclass(frozen=True)
class App:
    name: str
    path: Path
    bundle_id: str
    process: str
    opens_chat_shortcut: bool = False


APPS = {
    "copilot": App(
        name="Microsoft Copilot",
        path=Path("/Applications/Copilot.app"),
        bundle_id="com.microsoft.m365copilot",
        process="Copilot",
    ),
    "vscode": App(
        name="VS Code GitHub Copilot Chat",
        path=Path("/Applications/Visual Studio Code.app"),
        bundle_id="com.microsoft.VSCode",
        process="Code",
        opens_chat_shortcut=True,
    ),
    "gemini": App(
        name="Gemini",
        path=Path("/Applications/Gemini.app"),
        bundle_id="com.google.GeminiMacOS",
        process="Gemini",
    ),
}


class BridgeError(RuntimeError):
    """An expected error while invoking a local app."""


def ask(app_name: str, prompt: str) -> str:
    """Submit a prompt to an allowlisted app and read its visible reply."""
    if app_name not in APPS:
        raise BridgeError(f"Unsupported app: {app_name}")
    if not isinstance(prompt, str) or not prompt.strip():
        raise BridgeError("Prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise BridgeError(f"Prompt must be at most {MAX_PROMPT_LENGTH} characters")
    if not NATIVE_HELPER.is_file():
        raise BridgeError(f"Native UI helper was not found: {NATIVE_HELPER}")

    app = APPS[app_name]
    if not app.path.is_dir():
        raise BridgeError(f"{app.name} was not found at {app.path}")

    try:
        subprocess.run(
            ["open", "-a", str(app.path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        result = subprocess.run(
            [
                "/usr/bin/swift",
                str(NATIVE_HELPER),
                app.bundle_id,
                app.process,
                "yes" if app.opens_chat_shortcut else "no",
                prompt,
                str(RESPONSE_TIMEOUT_SECONDS),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=RESPONSE_TIMEOUT_SECONDS + 45,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeError(f"Timed out while communicating with {app.name}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Native UI automation failed").strip()
        raise BridgeError(detail) from exc

    response = result.stdout.strip()
    if not response:
        raise BridgeError(f"{app.name} returned no readable response text")
    return response
