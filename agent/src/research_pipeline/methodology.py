# -*- coding: utf-8 -*-
"""方法论注入（Core）：宪法全文 + calc SPEC，注入每阶段提示词正文。

文件缺失时**拒跑**（不是降级）：没有方法论的 agent 跑出来的东西不如不跑。
"""

from __future__ import annotations

from pathlib import Path

# agent/methodology/（src/research_pipeline 的上两级是 agent/）
METHODOLOGY_DIR = Path(__file__).resolve().parents[2] / "methodology"

_REQUIRED_FILES = ("constitution.md", "calc_spec.md")


def methodology_missing(env_dir: "str | Path | None" = None) -> "list[str]":
    """缺失的方法论文件清单（空 = 齐全）。env_dir 供测试注入临时目录。"""
    base = Path(env_dir) if env_dir else METHODOLOGY_DIR
    return [name for name in _REQUIRED_FILES if not (base / name).is_file()]


def _read(env_dir: "str | Path | None", name: str) -> str:
    base = Path(env_dir) if env_dir else METHODOLOGY_DIR
    return (base / name).read_text(encoding="utf-8")


def _strip_test_section(text: str) -> str:
    """剥掉 ``<!-- test-only -->`` 与 ``<!-- /test-only -->`` 之间的段落（给模型看的版本不含自检说明）。"""
    import re
    return re.sub(r"<!-- test-only -->.*?<!-- /test-only -->", "", text, flags=re.S).strip()


def methodology_block(stage: str, env_dir: "str | Path | None" = None) -> str:
    """注入提示词正文的方法论块：宪法全文 + calc SPEC（剥测试段）。"""
    missing = methodology_missing(env_dir)
    if missing:
        raise FileNotFoundError(f"方法论文件缺失，拒跑: {missing}（目录 {METHODOLOGY_DIR}）")
    constitution = _read(env_dir, "constitution.md").strip()
    calc_spec = _strip_test_section(_read(env_dir, "calc_spec.md"))
    return (
        "# 方法论（必须遵守）\n\n"
        f"{constitution}\n\n"
        f"---\n\n"
        f"{calc_spec}\n"
    )
