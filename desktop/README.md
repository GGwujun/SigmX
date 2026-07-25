# SigmX Desktop Client (Electron shell)

Wraps the existing SigmX web app (FastAPI backend + React frontend) in a native
desktop window. One Electron process = the whole app: it spawns the Python
backend (which serves the UI **and** runs the inline market-sync worker), waits
for `/health`, then opens a native `BrowserWindow` at `http://127.0.0.1:8899`.

```
Electron main process (Node)
  ├─ spawn: vibe-trading serve  (DESKTOP_MODE=1, START_WORKER=1)
  ├─ poll http://127.0.0.1:8899/health
  ├─ BrowserWindow.loadURL(http://127.0.0.1:8899/)   ← existing React UI
  └─ before-quit: taskkill /f /t the backend tree
```

The frontend is **reused unchanged** — it's still served by the Python backend.

## Dev mode

Spawns the backend from source (needs the repo + Python deps installed):

```bash
cd desktop
npm install
npm run dev          # SIGMX_DEV=1 → spawns `python -m api_server` from ../agent
```

A Python env with the `vibe-trading-ai` deps is required (`pip install -e .` in
the repo root). Override the interpreter with `SIGMX_PYTHON`.

## Packaged mode

After building the Python bundle (`pyinstaller ../vibe-trading.spec` →
`python-dist/`), `npm start` (no `SIGMX_DEV`) spawns the bundled executable:

```bash
npm install
npm run build:win    # → release/SigmX-Setup-<version>.exe (electron-builder)
```

The PyInstaller bundle is bundled as `extraResources/python-dist/`.

## Config

| Env | Default | Purpose |
|-----|---------|---------|
| `SIGMX_PORT` | 8899 | Backend listen port (loopback only) |
| `SIGMX_DEV` | unset | `1` = spawn backend from source instead of the bundle |
| `SIGMX_PYTHON` | `python` | Dev-mode interpreter |

The backend DB lives at the backend's default (`~/.vibe-trading/market.db`),
not bundled with the app, so it survives upgrades.

## Notes

- Auth is bypassed for loopback requests (`VIBE_TRADING_DESKTOP_MODE=1`); remote
  access still requires login.
- Remote read-only viewing: expose `127.0.0.1:8899` via Cloudflare Tunnel /
  Tailscale (configured outside this app).
