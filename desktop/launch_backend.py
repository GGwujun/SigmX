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
        # PyInstaller sets sys._MEIPASS (onefile) or leaves files next to the exe (onedir).
        base = getattr(sys, "_MEIPASS", None) or here
        frontend_dist = os.path.join(base, "frontend", "dist")
        if os.path.isdir(frontend_dist):
            os.environ.setdefault("SIGMX_FRONTEND_DIST", frontend_dist)

    from api_server import serve_main

    # Accept `serve` subcommand shape so the same arg parsing applies.
    return serve_main(["serve", "--port", port, "--host", "127.0.0.1"])


if __name__ == "__main__":
    raise SystemExit(main())
