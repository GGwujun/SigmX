"""PyInstaller entry point for the desktop client backend.

Builds the FastAPI server in desktop mode: loopback skips JWT auth and the
market-sync worker runs as an in-process daemon thread, so a single process
both serves the UI and pulls A-share data. Spawned by the Electron main
process; not meant to be run by hand (use `vibe-trading serve` for that).
"""
import os
import sys


def main() -> int:
    # Defaults for the bundled desktop client. Overridable via env.
    os.environ.setdefault("VIBE_TRADING_DESKTOP_MODE", "1")
    os.environ.setdefault("VIBE_TRADING_START_MARKET_SYNC_WORKER", "1")
    port = os.environ.get("VIBE_TRADING_PORT", "8899")

    # The frontend bundle is shipped as a sibling of the executable in onedir
    # builds; make the backend look there for dist/.
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: datas land in _internal/ next to the exe.
        # sys._MEIPASS is only set in onefile mode; in onedir, check both
        # <exe_dir>/_internal/frontend/dist/desktop and the equivalent
        # non-_internal location.
        base = getattr(sys, "_MEIPASS", None) or here
        candidates = [
            os.path.join(base, "_internal", "frontend", "dist", "desktop"),
            os.path.join(base, "frontend", "dist", "desktop"),
        ]
        for d in candidates:
            if os.path.isdir(d):
                os.environ.setdefault("SIGMX_FRONTEND_DIST", d)
                break

    from api_server import serve_main

    # serve_main reads VIBE_TRADING_PORT/HOST from env as defaults; pass them
    # explicitly too so the packaged exe is unambiguous.
    return serve_main(["--port", port, "--host", "127.0.0.1"])


if __name__ == "__main__":
    raise SystemExit(main())
