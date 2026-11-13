"""Build and validate the CP0 manifest for the Vietnamese Wikipedia corpus."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "vi_wikipedia_computing"
CATALOG_PATH = CORPUS_DIR / "source_catalog.json"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
MIN_UNITS = 30
MIN_UNIT_CHARS = 1_500


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        normalized = re.sub(r"[ \t\f\v]+", " ", paragraph)
        normalized = re.sub(r" *\n *", "\n", normalized).strip()
        if normalized:
            paragraphs.append(normalized)
    return "\n\n".join(paragraphs)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest() -> dict[str, object]:
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(
            "Vietnamese corpus snapshot is absent; run starter/scripts/download_vi_wikipedia.py"
        )
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    articles = catalog["articles"]
    if catalog.get("license", {}).get("spdx") != "CC-BY-SA-4.0":
        raise ValueError("Corpus catalog must record the CC-BY-SA-4.0 license")
    if len(articles) < MIN_UNITS:
        raise ValueError(f"Corpus has only {len(articles)} articles; at least {MIN_UNITS} are required")
    if len({int(article["pageid"]) for article in articles}) != len(articles):
        raise ValueError("Corpus catalog contains duplicate MediaWiki page IDs")
    if len({str(article["path"]) for article in articles}) != len(articles):
        raise ValueError("Corpus catalog contains duplicate local paths")

    files: list[dict[str, object]] = []
    units: list[dict[str, object]] = []
    for sequence, article in enumerate(articles, start=1):
        expected_category = catalog["collections"].get(article["collection"])
        if expected_category != article["source_category"]:
            raise ValueError(f"Untrusted collection mapping for page {article['pageid']}")
        if not str(article["canonical_url"]).startswith("https://vi.wikipedia.org/wiki/"):
            raise ValueError(f"Invalid canonical URL for page {article['pageid']}")
        if not isinstance(article["revision_id"], int) or article["revision_id"] <= 0:
            raise ValueError(f"Invalid revision ID for page {article['pageid']}")
        path = ROOT / article["path"]
        if not path.is_file():
            raise FileNotFoundError(f"Missing corpus file: {path}")
        if sha256(path) != article["sha256"]:
            raise ValueError(f"Checksum mismatch: {article['path']}")
        normalized = normalize_text(path.read_text(encoding="utf-8"))
        if len(normalized) != article["normalized_character_count"]:
            raise ValueError(f"Normalized length mismatch: {article['path']}")
        if len(normalized) < MIN_UNIT_CHARS:
            raise ValueError(f"Corpus unit shorter than {MIN_UNIT_CHARS}: {article['path']}")
        record = {
            "path": article["path"], "source_id": f"viwiki-{article['pageid']}",
            "title": article["title"], "canonical_url": article["canonical_url"],
            "revision_id": article["revision_id"],
            "revision_timestamp": article["revision_timestamp"],
            "collection": article["collection"], "source_category": article["source_category"],
            "sha256": article["sha256"],
            "normalized_character_count": len(normalized), "unit_count": 1,
        }
        files.append(record)
        units.append({
            "unit_id": f"viwiki-{article['pageid']}-u01", "source_id": record["source_id"],
            "source_path": article["path"], "title": article["title"],
            "collection": article["collection"], "sequence": sequence,
            "sequence_in_source": 1, "normalized_start": 0,
            "normalized_end": len(normalized), "character_count": len(normalized),
        })

    collections = sorted({str(unit["collection"]) for unit in units})
    if len(collections) < 2:
        raise ValueError("The collection filter needs at least two distinct values")
    return {
        "manifest_version": 2, "generated_at": "2026-11-13",
        "source": {
            "source_id": "vi-wikipedia-computing-snapshot-2026-11-13",
            "title": "Điện toán và ngôn ngữ lập trình — Wikipedia tiếng Việt",
            "source_path_or_url": "https://vi.wikipedia.org/", "api_url": catalog["api"],
            "version": "MediaWiki revision snapshot per article",
            "accessed_at": catalog["created_at"],
            "license_or_permission": catalog["license"]["name"],
            "license_spdx": catalog["license"]["spdx"],
            "license_url": catalog["license"]["url"],
            "terms_url": catalog["license"]["terms_url"],
            "attribution": catalog["license"]["attribution"],
            "local_catalog_path": CATALOG_PATH.relative_to(ROOT).as_posix(),
        },
        "counting_method": {
            "content_type": "non-paginated plain-text snapshots of independent articles",
            "rule": (
                "Each independently authored Wikipedia article is one meaningful source unit; "
                "this snapshot additionally requires at least 1,500 normalized characters per unit"
            ),
            "normalization": (
                "Unicode NFC; LF newlines; horizontal whitespace collapsed; blank lines reduced "
                "to paragraph separators"
            ),
            "minimum_characters_per_unit": MIN_UNIT_CHARS,
            "selection_rule": catalog["selection_rule"],
            "excluded_content": (
                "Category pages, redirects, references-only navigation and articles below the "
                "length threshold"
            ),
        },
        "filter_metadata": {
            "field": "collection",
            "source": "MediaWiki category membership recorded by the acquisition API",
            "distinct_values": collections,
            "purpose": (
                "Restrict retrieval when supplied context identifies programming-language or "
                "computer-science scope"
            ),
        },
        "summary": {
            "content_file_count": len(files), "content_unit_count": len(units),
            "normalized_character_count_in_units": sum(
                int(unit["character_count"]) for unit in units
            ),
            "minimum_unit_character_count": min(int(unit["character_count"]) for unit in units),
            "maximum_unit_character_count": max(int(unit["character_count"]) for unit in units),
            "collection_counts": {
                value: sum(unit["collection"] == value for unit in units)
                for value in collections
            },
        },
        "files": files, "units": units,
    }


def main() -> None:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = manifest["summary"]
    print(
        "Manifest OK: "
        f"{summary['content_unit_count']} independent units, "
        f"{summary['normalized_character_count_in_units']} normalized characters, "
        f"minimum {summary['minimum_unit_character_count']} characters/unit, "
        f"collections={summary['collection_counts']}"
    )


if __name__ == "__main__":
    main()
