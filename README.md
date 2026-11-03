# mac-ai-bridge

Send a prompt to an AI app already signed in on your Mac and read the reply
through its visible interface. This project uses Python's standard library and
macOS Accessibility/AppleScript UI automation; it does not use AI provider APIs
or require API keys. Gemini is GUI/AppleScript-only.

Supported targets:

| Target | CLI name | App |
| --- | --- | --- |
| Microsoft Copilot | `copilot` | `/Applications/Copilot.app` |
| GitHub Copilot Chat | `vscode` | `/Applications/Visual Studio Code.app` |
| Gemini | `gemini` | `/Applications/Gemini.app` |

## Requirements and permissions

- macOS with Python 3.9+ and the target app installed and signed in.
- Enable **System Settings → Privacy & Security → Accessibility** for the
  terminal or Python process running the bridge. macOS may also ask permission
  to control the app.
- In VS Code, have a workspace open and GitHub Copilot Chat available. The
  bridge opens Chat with VS Code's `Control+Command+I` shortcut.

The bridge activates the app, sends the prompt through an accessible text
input, and reads newly visible accessibility text from the front window. The
apps can change their UI, so an input/reply that is not exposed accessibly will
produce an explicit error. The bridge does not bypass sign-in, subscriptions,
or app access controls.

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
