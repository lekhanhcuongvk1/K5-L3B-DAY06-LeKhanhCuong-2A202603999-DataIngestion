"""Build and validate the CP0 manifest for the Python Tutorial corpus."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "python_tutorial"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
MIN_UNIT_CHARS = 1_500
TARGET_UNIT_CHARS = 3_500
EXCLUDED_FILES = {"index.txt", "LICENSE.txt"}

CHAPTERS = {
    "appetite.txt": "01_whetting_your_appetite",
    "interpreter.txt": "02_using_the_python_interpreter",
    "introduction.txt": "03_informal_introduction",
    "controlflow.txt": "04_control_flow",
    "datastructures.txt": "05_data_structures",
    "modules.txt": "06_modules",
    "inputoutput.txt": "07_input_and_output",
    "errors.txt": "08_errors_and_exceptions",
    "classes.txt": "09_classes",
    "stdlib.txt": "10_standard_library",
    "stdlib2.txt": "11_standard_library_part_2",
    "venv.txt": "12_virtual_environments",
    "whatnow.txt": "13_what_now",
    "interactive.txt": "14_interactive_input_editing",
    "floatingpoint.txt": "15_floating_point_arithmetic",
    "appendix.txt": "16_appendix",
}


def normalize_text(text: str) -> str:
    """Normalize Unicode/newlines while preserving paragraph boundaries."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        normalized = re.sub(r"[ \t\f\v]+", " ", paragraph)
        normalized = re.sub(r" *\n *", "\n", normalized).strip()
        if normalized:
            paragraphs.append(normalized)
    return "\n\n".join(paragraphs)


def split_units(text: str) -> list[str]:
    """Create ordered, paragraph-aligned units with at least 1,500 characters."""
    paragraphs = text.split("\n\n")
    units: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if current else 0)
        if current and current_length >= MIN_UNIT_CHARS and current_length + addition > TARGET_UNIT_CHARS:
            units.append("\n\n".join(current))
            current = []
            current_length = 0
        current.append(paragraph)
        current_length += len(paragraph) + (2 if len(current) > 1 else 0)

    if current:
        tail = "\n\n".join(current)
        if units and len(tail) < MIN_UNIT_CHARS:
            units[-1] = f"{units[-1]}\n\n{tail}"
        else:
            units.append(tail)

    if any(len(unit) < MIN_UNIT_CHARS for unit in units):
        raise ValueError("A generated content unit is shorter than 1,500 normalized characters")
    return units


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest() -> dict[str, object]:
    units: list[dict[str, object]] = []
    files: list[dict[str, object]] = []
    total_characters = 0

    for filename, chapter in CHAPTERS.items():
        path = CORPUS_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing corpus file: {path}")
        normalized = normalize_text(path.read_text(encoding="utf-8"))
        chapter_units = split_units(normalized)
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "chapter": chapter,
                "sha256": sha256(path),
                "normalized_character_count": len(normalized),
                "unit_count": len(chapter_units),
            }
        )
        offset = 0
        for number, unit_text in enumerate(chapter_units, start=1):
            start = normalized.find(unit_text, offset)
            end = start + len(unit_text)
            unit_id = f"py311-{chapter.split('_', 1)[0]}-u{number:02d}"
            units.append(
                {
                    "unit_id": unit_id,
                    "source_path": path.relative_to(ROOT).as_posix(),
                    "chapter": chapter,
                    "sequence_in_chapter": number,
                    "normalized_start": start,
                    "normalized_end": end,
                    "character_count": len(unit_text),
                }
            )
            offset = end
            total_characters += len(unit_text)

    if len(units) < 30:
        raise ValueError(f"Corpus has only {len(units)} units; at least 30 are required")
    if len({unit["chapter"] for unit in units}) < 2:
        raise ValueError("The chapter filter needs at least two distinct values")

    return {
        "manifest_version": 1,
        "generated_at": "2026-11-13",
        "source": {
            "source_id": "python-tutorial-3.11.18",
            "title": "The Python Tutorial — Python 3.11.18 documentation",
            "source_path_or_url": "https://docs.python.org/3.11/tutorial/",
            "download_url": "https://docs.python.org/3.11/archives/python-3.11.18-docs-text.zip",
            "version": "3.11.18",
            "accessed_at": "2026-11-13",
            "license_or_permission": "Python Software Foundation License Version 2",
            "license_url": "https://docs.python.org/3.11/license.html",
            "copyright_notice": "Copyright © 2001-2026 Python Software Foundation; All Rights Reserved",
            "local_license_path": "data/python_tutorial/LICENSE.txt",
        },
        "counting_method": {
            "content_type": "non-paginated plain text",
            "rule": "Ordered paragraph-aligned units, each with at least 1,500 normalized characters",
            "normalization": "Unicode NFC; LF newlines; repeated horizontal whitespace collapsed; blank lines reduced to paragraph separators",
            "minimum_characters_per_unit": MIN_UNIT_CHARS,
            "excluded_files": sorted(EXCLUDED_FILES),
            "exclusion_reason": "Navigation index and license text are retained for provenance but not counted as tutorial content",
        },
        "filter_metadata": {
            "field": "chapter",
            "source": "Official tutorial file/chapter boundaries in the downloaded archive",
            "distinct_values": list(CHAPTERS.values()),
            "purpose": "Disambiguate retrieval when a question or supplied context identifies a tutorial chapter",
        },
        "summary": {
            "content_file_count": len(files),
            "content_unit_count": len(units),
            "normalized_character_count_in_units": total_characters,
            "minimum_unit_character_count": min(unit["character_count"] for unit in units),
            "maximum_unit_character_count": max(unit["character_count"] for unit in units),
        },
        "files": files,
        "units": units,
    }


def main() -> None:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = manifest["summary"]
    print(
        "Manifest OK: "
        f"{summary['content_unit_count']} units, "
        f"{summary['normalized_character_count_in_units']} normalized characters, "
        f"minimum {summary['minimum_unit_character_count']} characters/unit"
    )


if __name__ == "__main__":
    main()
