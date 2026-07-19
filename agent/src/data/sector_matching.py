"""Conservative sector-name matching across market-data providers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar


_Row = TypeVar("_Row", bound=Mapping[str, Any])


def sector_name_keys(value: Any) -> tuple[str, str]:
    """Return an exact key and a conservative provider-neutral key."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = re.sub(r"[\s\u00b7\u2022_\-/]+", "", text)
    exact = text
    canonical = re.sub(
        r"[\(（][^\)）]*(?:申万|同花顺|东财|东方财富|中信)[^\)）]*[\)）]",
        "",
        text,
    )
    previous = ""
    while canonical and canonical != previous:
        previous = canonical
        canonical = re.sub(r"(?:行业|板块|概念|指数|分类)$", "", canonical)
        canonical = re.sub(r"(?:i{1,3}|iv|v|vi{0,3}|[一二三四五六七八九十]+级?)$", "", canonical)
    return exact, canonical


def match_sector_row(name: str, rows: Sequence[_Row]) -> _Row | None:
    """Return a sector row only when exact or canonical identity is unique.

    Exact identity (after NFKC/suffix normalization) always wins.  The
    provider-neutral canonical form handles cross-source naming differences
    like "半导体" vs "半导体板块".  Genuine ambiguity — two *different* sectors
    sharing a canonical key, e.g. 申万一级 "银行Ⅰ" and 二级 "银行Ⅱ" both
    reducing to "银行" — stays None, because picking either would silently
    misattribute capital flow to the wrong classification level.
    """
    target_exact, target_canonical = sector_name_keys(name)
    if not target_exact:
        return None
    keyed = [
        (row, *sector_name_keys(row.get("name") or row.get("sector")))
        for row in rows
        if row.get("name") or row.get("sector")
    ]
    exact_matches = [row for row, exact, _ in keyed if exact == target_exact]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if not target_canonical:
        return None
    canonical_matches = [
        row for row, _, canonical in keyed if canonical == target_canonical
    ]
    return canonical_matches[0] if len(canonical_matches) == 1 else None
