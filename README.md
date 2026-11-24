# ALICE Sovereign

ALICE is a Windows x64 desktop assistant with an Electron dashboard and a local Python runtime. This repository contains the application source used for the ALICE Sovereign 5.0.0 release.

## Source layout

- `nus/` — ALICE desktop app, dashboard, Knot interface, and Electron packaging configuration.
- `alice/` — Python runtime and local capabilities.
- `build-alice-nus.ps1` — builds the local Python sidecar.
- `requirements.txt` and `nus/package-lock.json` — runtime and desktop dependencies.

## Build on Windows

Requirements: Node.js 18 or newer, Python with the packages in `requirements.txt`, and the Kokoro voice assets described in `nus/vendor/voice/kokoro-multi-lang-v1_0/ALICE_VOICE_PACKAGE.md`.

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
.\build-alice-nus.ps1
Set-Location .\nus
npm ci
npm run dist:win
```

The large voice model files are intentionally not stored in this source repository. Place the required, properly licensed Kokoro assets in the documented directory before building the installer. The build script creates `alice-runtime-dist/`; generated build output, dependencies, model weights, and installer binaries are not tracked here.

## License

ALICE-authored code is released under MIT; see `LICENSE`. Third-party code and assets remain under their upstream terms. Nūs-derived portions are covered by Apache-2.0 and its notice is included in `LICENSES/Apache-2.0.txt`; the Nūs and Knot marks remain their respective owners' trademarks. Voice assets are not included; their upstream license and package note are kept in the source tree.
