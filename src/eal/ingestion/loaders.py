"""
Ingestion layer: load raw inputs and return source-traced bundles.

All loaders return plain text/dict — no IR construction here.
Source traceability (file path) is preserved for the extraction layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


class SpecDocument:
    """Raw markdown spec with source traceability."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text
        self.lines = text.splitlines()

    def sections(self) -> dict[str, list[str]]:
        """Split on ## headings → {heading_text: [lines]}."""
        result: dict[str, list[str]] = {}
        current: Optional[str] = None
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                current = stripped[3:].strip()
                result[current] = []
            elif current is not None:
                result[current].append(line)
        return result


class ModelDocument:
    """Raw YAML model with source traceability."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self.data = data


class CodeFile:
    """Raw Python source file."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text
        self.lines = text.splitlines()


def load_spec(path: Path) -> SpecDocument:
    text = path.read_text(encoding="utf-8")
    return SpecDocument(path=path, text=text)


def load_model(path: Path) -> ModelDocument:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return ModelDocument(path=path, data=data)


def load_code_files(paths: list[Path]) -> list[CodeFile]:
    result = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
            result.append(CodeFile(path=p, text=text))
        except OSError:
            pass
    return result
