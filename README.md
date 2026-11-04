# mac-ai-bridge

Send a prompt to an AI app already signed in on your Mac and read the reply
through its visible interface. This project uses Python's standard library and
native macOS UI automation; it does not use AI provider APIs or require API
keys. Gemini is GUI-only.

Supported targets:

| Target | CLI name | App |
| --- | --- | --- |
| Microsoft Copilot | `copilot` | `/Applications/Copilot.app` |
| GitHub Copilot Chat | `vscode` | `/Applications/Visual Studio Code.app` |
| Gemini | `gemini` | `/Applications/Gemini.app` |

## Requirements and permissions

- macOS 14+ with Python 3.9+ and the target app installed and signed in.
- Enable **System Settings → Privacy & Security → Accessibility** and
  **Screen Recording** for the terminal or app running the bridge. These are
  needed to send keyboard/mouse events and read the target app's visible window.
- The first `ask` compiles/runs a small Swift helper using macOS ScreenCaptureKit
  and Vision; Xcode Command Line Tools (including `swift`) must be installed.
- In VS Code, have a workspace open and GitHub Copilot Chat available. The
  bridge opens Chat with VS Code's `Control+Command+I` shortcut.

The bridge activates the app, focuses the chat composer (the VS Code shortcut,
or a click near the bottom of the Copilot/Gemini window), pastes the prompt,
and presses Return. It reads the resulting visible window using on-device OCR.
This avoids depending on AXTextField/AXTextArea, which these Electron/WebView
apps may not expose. App layout changes, hidden windows, denied macOS
permissions, or replies outside the visible window produce an explicit error.
The bridge does not bypass sign-in, subscriptions, or app access controls.

## CLI

From the project directory:

```sh
python3 -m mac_ai_bridge ask copilot "Summarize the latest release notes"
python3 -m mac_ai_bridge ask vscode "Explain the current file"
python3 -m mac_ai_bridge ask gemini "Suggest three names for a project"
```

## Local HTTP bridge

Start the server (it binds only to `127.0.0.1`):

```sh
python3 -m mac_ai_bridge serve
```

Ask and receive plain-text output:

```sh
curl -sS http://127.0.0.1:8765/ask \
  -H 'Content-Type: application/json' \
  -d '{"app":"copilot","prompt":"Explain what localhost means"}'
```

`app` is optional and defaults to `copilot`; allowed values are `copilot`,
`vscode`, and `gemini`. `GET /health` reports the available targets. Requests
are limited to 8,000 prompt characters and 16 KiB total body size.

The server accepts requests only over loopback and never logs prompt or reply
content. It has no authentication, so any process on this Mac can use it while
running. Do not expose it through a proxy, port forward, or non-loopback
interface. Stop it with `Ctrl+C`.

## Test

```sh
python3 -m unittest discover -s tests -v
```
