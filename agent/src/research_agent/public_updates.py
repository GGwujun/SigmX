"""Streaming extraction of explicitly public research-agent updates."""

from __future__ import annotations


def _prefix_suffix_length(value: str, marker: str) -> int:
    """Return the longest suffix of *value* that may start *marker*."""
    upper = min(len(value), len(marker) - 1)
    for length in range(upper, 0, -1):
        if value.endswith(marker[:length]):
            return length
    return 0


class PublicUpdateStreamParser:
    """Expose only text wrapped in ``public_update`` tags.

    The parser is intentionally independent from the LLM provider and accepts
    arbitrary chunk boundaries. Text outside the explicit tags is discarded.
    """

    OPEN = "<public_update>"
    CLOSE = "</public_update>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        output: list[str] = []
        while self._buffer:
            marker = self.CLOSE if self._inside else self.OPEN
            index = self._buffer.find(marker)
            if index >= 0:
                if self._inside and index:
                    output.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(marker):]
                self._inside = not self._inside
                continue

            keep = _prefix_suffix_length(self._buffer, marker)
            confirmed = self._buffer[:-keep] if keep else self._buffer
            if self._inside and confirmed:
                output.append(confirmed)
            self._buffer = self._buffer[-keep:] if keep else ""
            break
        return output

    def finish(self) -> list[str]:
        self._buffer = ""
        self._inside = False
        return []
