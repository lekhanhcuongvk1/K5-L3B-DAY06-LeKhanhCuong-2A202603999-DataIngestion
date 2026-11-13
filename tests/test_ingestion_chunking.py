from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.src.chunking import by_paragraph, fixed_size
from starter.src.ingestion import load_text_manifest, normalize_text
from starter.src.models import DocumentPage


ROOT = Path(__file__).resolve().parents[1]


def sample_page(text: str = "abcdefghij") -> DocumentPage:
    return DocumentPage(
        document_id="doc",
        source="source.txt",
        page=None,
        unit_id="unit-01",
        sequence=1,
        text=text,
        metadata={"chapter": "chapter_1", "version": "1"},
    )


class NormalizeTests(unittest.TestCase):
    def test_unicode_whitespace_and_paragraphs(self) -> None:
        raw = "  Tiếng   Việt  \r\n dòng hai\r\n\r\n  Đoạn\t mới  "
        normalized = normalize_text(raw)
        self.assertEqual(normalized, "Tiếng Việt\ndòng hai\n\nĐoạn mới")

    def test_empty_text(self) -> None:
        self.assertEqual(normalize_text(" \n\t\n "), "")


class FixedChunkTests(unittest.TestCase):
    def test_overlap_and_complete_coverage(self) -> None:
        chunks = fixed_size(sample_page(), size=5, overlap=2)
        self.assertEqual([(c.char_start, c.char_end) for c in chunks], [(0, 5), (3, 8), (6, 10)])
        self.assertEqual(chunks[0].text[-2:], chunks[1].text[:2])
        covered = {index for chunk in chunks for index in range(chunk.char_start, chunk.char_end)}
        self.assertEqual(covered, set(range(10)))

    def test_invalid_parameters_and_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            fixed_size(sample_page(), 0, 0)
        with self.assertRaises(ValueError):
            fixed_size(sample_page(), 5, 5)
        self.assertEqual(fixed_size(sample_page(""), 5, 1), [])

    def test_ids_and_metadata_are_stable(self) -> None:
        first = fixed_size(sample_page(), 5, 1)
        second = fixed_size(sample_page(), 5, 1)
        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])
        self.assertTrue(all(chunk.unit_id == "unit-01" for chunk in first))
        self.assertTrue(all(chunk.metadata["chapter"] == "chapter_1" for chunk in first))


class ParagraphChunkTests(unittest.TestCase):
    def test_prefers_paragraph_boundaries_without_gaps(self) -> None:
        page = sample_page("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")
        chunks = by_paragraph(page, max_size=34)
        self.assertEqual("".join(chunk.text for chunk in chunks), page.text)
        self.assertTrue(all(len(chunk.text) <= 34 for chunk in chunks))
        self.assertEqual(chunks[0].char_start, 0)
        self.assertEqual(chunks[-1].char_end, len(page.text))

    def test_splits_oversized_paragraph_and_handles_edges(self) -> None:
        page = sample_page("x" * 25)
        chunks = by_paragraph(page, max_size=10)
        self.assertEqual([len(chunk.text) for chunk in chunks], [10, 10, 5])
        self.assertEqual("".join(chunk.text for chunk in chunks), page.text)
        with self.assertRaises(ValueError):
            by_paragraph(page, 0)
        self.assertEqual(by_paragraph(sample_page(""), 10), [])

    def test_separator_at_size_boundary_never_exceeds_limit(self) -> None:
        page = sample_page("x" * 9 + "\n\n" + "tail")
        chunks = by_paragraph(page, max_size=10)
        self.assertTrue(all(len(chunk.text) <= 10 for chunk in chunks))
        self.assertEqual("".join(chunk.text for chunk in chunks), page.text)


class ManifestIngestionTests(unittest.TestCase):
    def test_real_manifest_loads_every_unit_with_traceability(self) -> None:
        manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
        units, errors = load_text_manifest(ROOT / "data" / "manifest.json")
        self.assertEqual(errors, [])
        self.assertEqual(len(units), manifest["summary"]["content_unit_count"])
        self.assertEqual(sum(len(unit.text) for unit in units), 231_959)
        self.assertTrue(all(unit.page is None for unit in units))
        self.assertTrue(all(unit.metadata["chapter"] for unit in units))
        self.assertEqual(len({unit.unit_id for unit in units}), len(units))

    def test_real_corpus_chunk_coverage_spans_and_metadata(self) -> None:
        units, errors = load_text_manifest(ROOT / "data" / "manifest.json")
        self.assertEqual(errors, [])
        for unit in units:
            chunks_a = fixed_size(unit, 500, 50)
            chunks_b = by_paragraph(unit, 1_000)
            covered_a = {
                index
                for chunk in chunks_a
                for index in range(chunk.char_start, chunk.char_end)
            }
            self.assertEqual(covered_a, set(range(len(unit.text))))
            self.assertEqual("".join(chunk.text for chunk in chunks_b), unit.text)
            for chunk in chunks_a + chunks_b:
                self.assertEqual(chunk.text, unit.text[chunk.char_start:chunk.char_end])
                self.assertEqual(chunk.document_id, unit.document_id)
                self.assertEqual(chunk.source, unit.source)
                self.assertEqual(chunk.unit_id, unit.unit_id)
                self.assertEqual(chunk.page, unit.page)
                self.assertEqual(chunk.metadata["chapter"], unit.metadata["chapter"])
                self.assertEqual(chunk.metadata["version"], unit.metadata["version"])
            self.assertTrue(all(len(chunk.text) <= 500 for chunk in chunks_a))
            self.assertTrue(all(len(chunk.text) <= 1_000 for chunk in chunks_b))

    def test_missing_declared_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            manifest = {
                "source": {"source_id": "doc", "version": "1"},
                "files": [{
                    "path": "data/missing.txt", "sha256": "none",
                    "normalized_character_count": 10,
                }],
                "units": [],
            }
            path = data / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            units, errors = load_text_manifest(path)
            self.assertEqual(units, [])
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].error_type, "missing_file")


if __name__ == "__main__":
    unittest.main()
