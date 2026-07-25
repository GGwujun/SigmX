# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the SigmX desktop client backend.
#
# Builds the FastAPI server (+ inline market-sync worker) as a onedir bundle
# that the Electron shell spawns. Run from the repo root:
#
#   pyinstaller vibe-trading.spec
#
# Output: dist/vibe-trading/  (point electron-builder's extraResources here, or
# copy to desktop/python-dist/). Build is onedir (not onefile): a 300MB+ frozen
# app starts far faster from a dir than re-extracting on every launch.
#
# Iterating on missing-module errors: bump `hiddenimports` below, rebuild.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# --- Dynamically-imported submodules that PyInstaller's static analysis misses ---
hidden = []
# FastAPI / Starlette / Pydantic: route discovery + pydantic core.
hidden += collect_submodules("fastapi")
hidden += collect_submodules("starlette")
hidden += collect_submodules("pydantic")
hidden += collect_submodules("pydantic_core")
hidden += ["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
           "uvicorn.protocols", "uvicorn.protocols.http.auto",
           "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
# LangChain / LangGraph: entry-point + schema heavy.
hidden += collect_submodules("langchain")
hidden += collect_submodules("langchain_core")
hidden += collect_submodules("langgraph")
# App route modules are imported by name in api_server; force them in.
hidden += collect_submodules("src")

datas = []
# Package data files (pydantic schemas, langchain json, etc.).
datas += collect_data_files("langchain")
datas += collect_data_files("langchain_core")
datas += collect_data_files("pydantic")
# The built React frontend is served by the backend; ship it inside the bundle.
import os
frontend_dist = os.path.join("frontend", "dist")
if os.path.isdir(frontend_dist):
    datas += [(frontend_dist, "frontend/dist")]

a = Analysis(
    ["desktop/launch_backend.py"],
    pathex=["agent"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim what we know the desktop client never needs.
        "tkinter", "pytest", "IPython", "notebook", "jupyter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vibe-trading",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep a console so backend logs are visible during bring-up
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vibe-trading",
)
