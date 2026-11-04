# mac-ai-bridge

Send a prompt to an AI app already signed in on your Mac and read the reply
through its visible interface. The UI bridge uses native macOS keyboard events,
the clipboard, ScreenCaptureKit, and on-device Vision OCR. It does not use AI
provider APIs or require API keys. Gemini is GUI-only.

Supported targets:

| Target | CLI name | App |
| --- | --- | --- |
| Microsoft Copilot | `copilot` | `/Applications/Copilot.app` |
| GitHub Copilot Chat | `vscode` | `/Applications/Visual Studio Code.app` |
| Gemini | `gemini` | `/Applications/Gemini.app` |

## Requirements and permissions

- macOS 14+ with Python 3.9+, Swift/Xcode Command Line Tools, and the target app
  installed and signed in.
- Enable **System Settings → Privacy & Security → Accessibility** and
  **Screen Recording** for the terminal or app running the bridge. The first
  run may request these permissions.
- In VS Code, have a workspace open and GitHub Copilot Chat available. The
  bridge opens Chat with VS Code's `Control+Command+I` shortcut.

The bridge does not require `AXTextField` or `AXTextArea`, which some Electron
and WebView apps do not expose. It activates the app, opens VS Code Chat with
the shortcut above (or clicks near the bottom of Copilot/Gemini), pastes the
prompt using macOS keyboard events, and reads the visible window with on-device
OCR until its text stabilizes. App layout changes, hidden windows, denied
permissions, or replies outside the visible window produce an explicit error.
Clipboard contents are restored after pasting. The bridge does not bypass
sign-in, subscriptions, or app access controls.

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
