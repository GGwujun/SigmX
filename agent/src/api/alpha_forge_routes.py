"""AlphaForge 投研报告 HTTP routes for the Web UI.

Mounted by ``agent/api_server.py`` via ``register_alpha_forge_routes(app, ...)``.

Routes:
- ``GET  /alpha-forge/reports``                  — list saved reports
- ``GET  /alpha-forge/reports/{report_id}``       — report detail (MD + metadata)
- ``GET  /alpha-forge/reports/{report_id}/download`` — download MD or PDF
- ``POST /alpha-forge/runs``                      — create a new AlphaForge run
- ``GET  /alpha-forge/runs/{run_id}``             — get run status
- ``GET  /alpha-forge/runs/{run_id}/events``      — SSE live progress

Report storage: ``~/.vibe-trading/alpha_forge_reports/``
Each report: ``{report_id}/report.md`` + ``{report_id}/meta.json``
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Report storage
# ---------------------------------------------------------------------------

REPORTS_ROOT = Path.home() / ".vibe-trading" / "alpha_forge_reports"

# SSE manager singleton — populated by register_alpha_forge_routes
_sse_manager: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AlphaForgeRunRequest(BaseModel):
    target: str = Field(..., description="目标股票代码，如 300253.SZ")
    market: str = Field(default="A-shares", description="市场")

class AlphaForgeRunResponse(BaseModel):
    run_id: str
    status: str
    target: str
    market: str
    created_at: str

class ReportMeta(BaseModel):
    report_id: str
    target: str
    stock_name: str = ""
    market: str
    analysis_date: str
    created_at: str
    signal: str = ""  # BUY / SELL / HOLD
    rating: str = ""  # Overweight / Equal-weight / Underweight

class ReportListItem(BaseModel):
    report_id: str
    target: str
    stock_name: str
    market: str
    analysis_date: str
    created_at: str
    signal: str
    rating: str

class ReportDetail(BaseModel):
    report_id: str
    target: str
    stock_name: str
    market: str
    analysis_date: str
    created_at: str
    signal: str
    rating: str
    content_md: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_reports_root() -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    """Remove dangerous characters from filenames."""
    return re.sub(r"[<>:\"/\\|?*]", "_", name)


def _extract_metadata_from_md(content: str) -> dict[str, str]:
    """Extract metadata from AlphaForge markdown report frontmatter."""
    meta: dict[str, str] = {}
    lines = content.split("\n")
    for line in lines[:20]:
        line = line.strip()
        if line.startswith("- **股票代码**") or line.startswith("- **股票代码**："):
            m = re.search(r"[-：:]\s*(\S+)", line)
            if m: meta["target"] = m.group(1)
        elif "**分析日期**" in line:
            m = re.search(r"[-：:]\s*(\S+)", line)
            if m: meta["analysis_date"] = m.group(1)
        elif "**生成时间**" in line:
            m = re.search(r"[-：:]\s*(\S+)", line)
            if m: meta["created_at"] = m.group(1)
        elif "**交易信号**" in line:
            m = re.search(r"\*\*(卖出|买入|持有|BUY|SELL|HOLD)\*\*", line)
            if m: meta["signal"] = m.group(1)
        elif "FINAL TRANSACTION PROPOSAL" in line:
            # Last one wins
            m = re.search(r"\*\*(SELL|BUY|HOLD)\*\*", line)
            if m: meta["signal"] = m.group(1)
        elif "**投资评级" in line or "最终投资评级" in line:
            m = re.search(r"[：:]\s*\**(\S+)\**", line)
            if m: meta["rating"] = m.group(1).strip("*")
    return meta


def _list_report_dirs() -> list[Path]:
    """List all report directories sorted by creation time (newest first)."""
    _ensure_reports_root()
    dirs = [d for d in REPORTS_ROOT.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs


def _load_report_meta(report_id: str) -> dict[str, Any] | None:
    """Load report metadata from meta.json."""
    meta_path = REPORTS_ROOT / report_id / "meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _load_report_md(report_id: str) -> str | None:
    """Load report markdown content."""
    md_path = REPORTS_ROOT / report_id / "report.md"
    if not md_path.exists():
        return None
    return md_path.read_text(encoding="utf-8")


def _save_report(report_id: str, content_md: str, meta: dict[str, Any]) -> Path:
    """Save a report to disk. Returns the report directory path."""
    _ensure_reports_root()
    report_dir = REPORTS_ROOT / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / "report.md").write_text(content_md, encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return report_dir


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_alpha_forge_routes(
    app: FastAPI,
    require_auth: Callable[[Request], Awaitable[None]],
    require_event_stream_auth: Callable[[Request], Awaitable[None]],
) -> None:
    """Register AlphaForge routes on the FastAPI app."""

    # ── List Reports ──────────────────────────────────────────────
    @app.get("/alpha-forge/reports")
    async def list_reports(request: Request, _=Depends(require_auth)):
        """List all saved AlphaForge reports."""
        reports: list[dict] = []
        for d in _list_report_dirs():
            meta = _load_report_meta(d.name)
            if meta:
                reports.append({
                    "report_id": d.name,
                    "target": meta.get("target", d.name),
                    "stock_name": meta.get("stock_name", ""),
                    "market": meta.get("market", "A-shares"),
                    "analysis_date": meta.get("analysis_date", ""),
                    "created_at": meta.get("created_at", ""),
                    "signal": meta.get("signal", ""),
                    "rating": meta.get("rating", ""),
                })
        return reports

    # ── Get Report Detail ─────────────────────────────────────────
    @app.get("/alpha-forge/reports/{report_id}")
    async def get_report(report_id: str, request: Request, _=Depends(require_auth)):
        """Get a full report with markdown content."""
        meta = _load_report_meta(report_id)
        content = _load_report_md(report_id)
        if meta is None or content is None:
            raise HTTPException(status_code=404, detail=f"Report {report_id!r} not found")

        return {
            "report_id": report_id,
            "target": meta.get("target", ""),
            "stock_name": meta.get("stock_name", ""),
            "market": meta.get("market", "A-shares"),
            "analysis_date": meta.get("analysis_date", ""),
            "created_at": meta.get("created_at", ""),
            "signal": meta.get("signal", ""),
            "rating": meta.get("rating", ""),
            "content_md": content,
        }

    # ── Download Report ───────────────────────────────────────────
    @app.get("/alpha-forge/reports/{report_id}/download")
    async def download_report(
        report_id: str,
        request: Request,
        format: str = Query("md", description="Download format: md or pdf"),
        _=Depends(require_auth),
    ):
        """Download a report as MD or PDF."""
        meta = _load_report_meta(report_id)
        content = _load_report_md(report_id)
        if meta is None or content is None:
            raise HTTPException(status_code=404, detail=f"Report {report_id!r} not found")

        target = meta.get("target", report_id)
        filename_base = f"AlphaForge_{target}_{meta.get('analysis_date', 'unknown')}"

        if format == "md":
            return Response(
                content=content,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{_sanitize_filename(filename_base)}.md"',
                },
            )

        if format == "pdf":
            # Check if PDF already exists (cached)
            pdf_path = REPORTS_ROOT / report_id / "report.pdf"
            if pdf_path.exists():
                return FileResponse(
                    pdf_path,
                    media_type="application/pdf",
                    filename=f"{_sanitize_filename(filename_base)}.pdf",
                )

            # Generate PDF with weasyprint
            try:
                import markdown as md_lib
                from weasyprint import HTML

                # Convert MD to HTML
                md_html = md_lib.markdown(
                    content,
                    extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"],
                )

                html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "Microsoft YaHei", "SimSun", sans-serif; font-size: 13px; line-height: 1.7; max-width: 210mm; margin: auto; padding: 20px; color: #333; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #999; padding-bottom: 4px; margin-top: 28px; }}
  h3 {{ font-size: 15px; margin-top: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 11px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: bold; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 10px 0; padding: 6px 16px; background: #f9f9f9; }}
  code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-size: 12px; }}
  pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 20px 0; }}
</style>
</head>
<body>{md_html}</body>
</html>"""

                pdf_bytes = HTML(string=html_template).write_pdf()
                # Cache PDF
                pdf_path.write_bytes(pdf_bytes)

                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'attachment; filename="{_sanitize_filename(filename_base)}.pdf"',
                    },
                )
            except ImportError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF generation dependency missing: {e}. Install weasyprint and markdown.",
                )
            except Exception as e:
                logger.error("PDF generation failed for %s: %s", report_id, e, exc_info=True)
                raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

        raise HTTPException(status_code=400, detail=f"Unknown format: {format!r}. Use 'md' or 'pdf'.")

    # ── Create AlphaForge Run ─────────────────────────────────────
    @app.post("/alpha-forge/runs")
    async def create_alpha_forge_run(
        body: AlphaForgeRunRequest,
        request: Request,
        _=Depends(require_auth),
    ):
        """Create a new AlphaForge analysis run using the swarm preset."""
        # We delegate to the swarm subsystem
        from src.swarm.presets import build_run_from_preset
        from src.swarm.runtime import SwarmRuntime
        from src.swarm.store import SwarmStore

        # Check preset exists
        try:
            run = build_run_from_preset("alpha_forge", {
                "target": body.target,
                "market": body.market,
            })
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="alpha_forge preset not found. Ensure alpha_forge.yaml is in presets/ directory.",
            )

        # Start the run via the global swarm runtime (set up in api_server.py)
        swarm_runtime = _sse_manager.get("swarm_runtime")
        if swarm_runtime is None:
            raise HTTPException(
                status_code=503,
                detail="Swarm runtime not available. Start the server with swarm support enabled.",
            )

        try:
            swarm_run = swarm_runtime.start_run(
                preset_name="alpha_forge",
                user_vars={"target": body.target, "market": body.market},
            )
        except Exception as e:
            logger.error("Failed to start alpha_forge run: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to start run: {e}")

        # Register a completion callback to save the report
        def _on_run_complete(run_id: str) -> None:
            """Save the final report when the swarm run completes."""
            try:
                from src.swarm.store import SwarmStore
                store = SwarmStore()
                completed_run = store.load_run(run_id)
                if completed_run is None or not completed_run.final_report:
                    logger.warning("No final report for run %s, skipping report save", run_id)
                    return

                content = completed_run.final_report
                # Generate report ID
                now = datetime.now(timezone.utc)
                ts = now.strftime("%Y%m%d-%H%M%S")
                report_id = f"af_{body.target.replace('.', '_')}_{ts}"

                # Extract stock name from report content
                stock_name = ""
                for line in content.split("\n")[:10]:
                    m = re.search(r"(\S+)\s*[（(]\s*{0}".format(body.target.split(".")[0]), line)
                    if not m:
                        m = re.search(r"#\s*[\d]+\s*[（(]?\s*(\S+)\s*[）)]?", line)
                    if m:
                        stock_name = m.group(1)
                        break

                meta = {
                    "target": body.target,
                    "stock_name": stock_name,
                    "market": body.market,
                    "analysis_date": now.strftime("%Y-%m-%d"),
                    "created_at": now.isoformat(),
                    "run_id": run_id,
                }
                # Extract signal and rating from content
                extra = _extract_metadata_from_md(content)
                meta.update(extra)

                _save_report(report_id, content, meta)
                logger.info("Saved AlphaForge report %s for %s", report_id, body.target)
            except Exception as e:
                logger.error("Failed to save AlphaForge report for run %s: %s", run_id, e, exc_info=True)

        # Register callback with the runtime
        swarm_runtime._live_callbacks[swarm_run.id] = lambda event: None  # placeholder
        # Use store to poll for completion — simpler: register via a background thread
        import threading
        def _poll_completion():
            import time as time_mod
            store_obj = __import__("src.swarm.store", fromlist=["SwarmStore"]).SwarmStore()
            while True:
                time_mod.sleep(5)
                try:
                    r = store_obj.load_run(swarm_run.id)
                    if r and r.status.value in ("completed", "failed", "cancelled"):
                        if r.status.value == "completed":
                            _on_run_complete(swarm_run.id)
                        break
                except Exception:
                    break
        threading.Thread(target=_poll_completion, daemon=True).start()

        return AlphaForgeRunResponse(
            run_id=swarm_run.id,
            status=swarm_run.status.value,
            target=body.target,
            market=body.market,
            created_at=swarm_run.created_at,
        )

    # ── Get Run Status ────────────────────────────────────────────
    @app.get("/alpha-forge/runs/{run_id}")
    async def get_alpha_forge_run(run_id: str, request: Request, _=Depends(require_auth)):
        """Get the status of an AlphaForge swarm run."""
        from src.swarm.store import SwarmStore
        store = SwarmStore()
        run = store.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        return {
            "run_id": run.id,
            "status": run.status.value,
            "preset_name": run.preset_name,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "final_report": run.final_report,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
            "tasks": [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "status": t.status.value,
                }
                for t in run.tasks
            ],
        }

    # ── SSE Events Stream ─────────────────────────────────────────
    @app.get("/alpha-forge/runs/{run_id}/events")
    async def stream_alpha_forge_events(
        run_id: str,
        request: Request,
        _=Depends(require_event_stream_auth),
    ):
        """SSE stream for live AlphaForge run progress."""
        from src.swarm.store import SwarmStore
        store = SwarmStore()

        # Verify run exists
        run = store.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        async def event_generator():
            events_file = store.run_dir(run_id) / "events.jsonl"
            last_pos = 0

            # Replay existing events
            if events_file.exists():
                try:
                    existing = events_file.read_text(encoding="utf-8")
                    yield f"data: {json.dumps({'type': 'replay_start', 'count': len(existing.splitlines())})}\n\n"
                    for line in existing.splitlines():
                        if line.strip():
                            yield f"data: {line.strip()}\n\n"
                    last_pos = events_file.stat().st_size
                except Exception:
                    pass

            # Watch for new events
            import time as time_mod
            while True:
                if await request.is_disconnected():
                    break
                try:
                    if events_file.exists():
                        current_size = events_file.stat().st_size
                        if current_size > last_pos:
                            with open(events_file, "r", encoding="utf-8") as f:
                                f.seek(last_pos)
                                new_data = f.read()
                                for line in new_data.splitlines():
                                    if line.strip():
                                        yield f"data: {line.strip()}\n\n"
                            last_pos = current_size
                except Exception:
                    pass

                # Check if run is done
                try:
                    current = store.load_run(run_id)
                    if current and current.status.value in ("completed", "failed", "cancelled"):
                        yield f"data: {json.dumps({'type': 'run_done', 'status': current.status.value})}\n\n"
                        break
                except Exception:
                    pass

                await asyncio.sleep(1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    logger.info("AlphaForge routes registered")
