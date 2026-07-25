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

# --- Data-source packages whose imports PyInstaller cannot statically trace ---
# A-share: mootdx (通达信免费行情), tushare (Pro REST API), tpdog (托普量化).
hidden += collect_submodules("mootdx")
hidden += collect_submodules("tushare")
hidden += collect_submodules("tpdog")
# Global / macro: akshare + its transitive deps.
hidden += collect_submodules("akshare")
# Free A-share data: bao stock (baostock).
hidden += collect_submodules("baostock")
hidden += collect_submodules("bs4")
hidden += collect_submodules("openpyxl")
hidden += collect_submodules("xlsxwriter")
hidden += collect_submodules("html5lib")
hidden += collect_submodules("jsonpath_ng")
hidden += collect_submodules("simplejson")
hidden += collect_submodules("six")

datas = []
# Package data files (pydantic schemas, langchain json, etc.).
datas += collect_data_files("langchain")
datas += collect_data_files("langchain_core")
datas += collect_data_files("pydantic")
# akshare ships a trade calendar JSON that is read at runtime.
datas += collect_data_files("akshare")

# App-specific data files that PyInstaller's static analysis misses.
import os
_agent_dir = os.path.join("agent")
# LLM provider config (json, required at import time).
_providers_json = os.path.join(_agent_dir, "src", "providers", "llm_providers.json")
if os.path.exists(_providers_json):
    datas += [(_providers_json, os.path.join("src", "providers"))]
# Swarm YAML presets.
_presets_dir = os.path.join(_agent_dir, "src", "swarm", "presets")
if os.path.isdir(_presets_dir):
    for _f in os.listdir(_presets_dir):
        if _f.endswith(".yaml") or _f.endswith(".yml"):
            _fp = os.path.join(_presets_dir, _f)
            if os.path.isfile(_fp):
                datas += [(_fp, os.path.join("src", "swarm", "presets"))]
# Prompts directory (markdown templates).
_prompts_dir = os.path.join(_agent_dir, "src", "prompts")
if os.path.isdir(_prompts_dir):
    for _root, _dirs, _files in os.walk(_prompts_dir):
        for _f in _files:
            _fp = os.path.join(_root, _f)
            _rel = os.path.relpath(_root, _agent_dir)
            datas += [(_fp, _rel)]

# The built React frontend is served by the backend; ship it inside the bundle.
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
