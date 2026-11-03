"""Accessibility-driven UI automation for supported Mac AI apps."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


MAX_PROMPT_LENGTH = 8_000
RESPONSE_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class App:
    name: str
    path: Path
    process: str
    opens_chat_shortcut: bool = False


APPS = {
    "copilot": App(
        name="Microsoft Copilot",
        path=Path("/Applications/Copilot.app"),
        process="Copilot",
    ),
    "vscode": App(
        name="VS Code GitHub Copilot Chat",
        path=Path("/Applications/Visual Studio Code.app"),
        process="Code",
        opens_chat_shortcut=True,
    ),
    "gemini": App(
        name="Gemini",
        path=Path("/Applications/Gemini.app"),
        process="Gemini",
    ),
}


class BridgeError(RuntimeError):
    """An expected error while invoking a local app."""


def _automation_script(app: App) -> str:
    """Build an AppleScript program; user prompt is passed separately as argv."""
    shortcut = ""
    if app.opens_chat_shortcut:
        shortcut = """
        tell process "Code"
            keystroke "i" using {control down, command down}
        end tell
        delay 1
        """

    return f'''
on run argv
    set userPrompt to item 1 of argv
    tell application "System Events"
        set processName to "{app.process}"
        repeat 30 times
            if exists process processName then exit repeat
            delay 0.5
        end repeat
        if not (exists process processName) then error "App process did not start"
        tell process processName
            set frontmost to true
        end tell
        delay 1
        {shortcut}
        tell process processName
            if (count of windows) is 0 then error "App has no open window"
            set targetWindow to front window
            set composer to missing value
            set focusedComposer to missing value
            set textFieldCandidate to missing value
            repeat with element in (entire contents of targetWindow)
                try
                    set elementRole to role of element
                    if elementRole is "AXTextArea" or elementRole is "AXTextField" then
                        set elementLabel to ""
                        try
                            set elementLabel to (description of element as text) & " " & (help of element as text) & " " & (name of element as text)
                        end try
                        if elementLabel contains "chat" or elementLabel contains "prompt" or elementLabel contains "message" or elementLabel contains "ask" then
                            set composer to element
                        end if
                        try
                            if focused of element then set focusedComposer to element
                        end try
                        if elementRole is "AXTextField" then set textFieldCandidate to element
                    end if
                end try
            end repeat
            if composer is missing value then set composer to focusedComposer
            if composer is missing value then set composer to textFieldCandidate
            if composer is missing value then error "Could not find an accessible chat input"
            set beforeText to my readVisibleText(targetWindow)
            try
                set focused of composer to true
                set value of composer to userPrompt
            on error
                click composer
                keystroke "a" using {{command down}}
                keystroke userPrompt
            end try
            key code 36
            delay 2
            set lastText to ""
            set stableCount to 0
            repeat 180 times
                delay 1
                set currentText to my readVisibleText(targetWindow)
                if currentText is not beforeText and currentText is not lastText then
                    set stableCount to 0
                else if currentText is not beforeText then
                    set stableCount to stableCount + 1
                end if
                set lastText to currentText
                if stableCount is greater than or equal to 8 then exit repeat
            end repeat
            if lastText is beforeText then error "No new response appeared in the app"
            if stableCount < 8 then error "Timed out waiting for the response to finish"
            set newLines to {{}}
            set oldLines to paragraphs of beforeText
            repeat with responseLine in paragraphs of lastText
                set lineText to contents of responseLine
                if lineText is not "" and lineText is not userPrompt and oldLines does not contain lineText then
                    set end of newLines to lineText
                end if
            end repeat
            if (count of newLines) is 0 then error "Could not isolate new response text"
            set AppleScript's text item delimiters to linefeed
            set resultText to newLines as text
            set AppleScript's text item delimiters to ""
            return resultText
        end tell
    end tell
end run

on readVisibleText(targetWindow)
    tell application "System Events"
        set visibleText to ""
        repeat with element in (entire contents of targetWindow)
            try
                if role of element is "AXStaticText" or role of element is "AXTextArea" then
                    set elementValue to value of element as text
                    if elementValue is not "" then set visibleText to visibleText & elementValue & linefeed
                end if
            end try
        end repeat
        return visibleText
    end tell
end readVisibleText
'''


def ask(app_name: str, prompt: str) -> str:
    """Submit a prompt to an allowlisted, signed-in app and return visible reply text."""
    if app_name not in APPS:
        raise BridgeError(f"Unsupported app: {app_name}")
    if not isinstance(prompt, str) or not prompt.strip():
        raise BridgeError("Prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise BridgeError(f"Prompt must be at most {MAX_PROMPT_LENGTH} characters")

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
                "/usr/bin/osascript",
                "-e",
                _automation_script(app),
                "--",
                prompt,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=RESPONSE_TIMEOUT_SECONDS + 20,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeError(f"Timed out while communicating with {app.name}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "AppleScript automation failed").strip()
        raise BridgeError(detail) from exc

    response = result.stdout.strip()
    if not response:
        raise BridgeError(f"{app.name} returned no readable response text")
    return response
