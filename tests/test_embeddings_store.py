from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from starter.src.embeddings import MyEmbedder
from starter.src.models import Chunk
from starter.src.store import PgVectorStore


ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "starter"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class RealEmbeddingAndStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        load_dotenv(STARTER / ".env")
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise unittest.SkipTest("DATABASE_URL is not configured")
        cls.database_url = database_url
        cls.embedder = MyEmbedder(MODEL, device="cpu", batch_size=4)
        cls.store = PgVectorStore(database_url, cls.embedder.dimensions)
        cls.store.create_schema()

    def test_real_document_and_query_embeddings(self) -> None:
        vectors = self.embedder.embed_documents(["Python module", "virtual environment"])
        query = self.embedder.embed_query("Môi trường ảo Python")
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(query), 384)
        self.assertTrue(all(len(vector) == 384 for vector in vectors))
        self.assertTrue(all(math.isfinite(value) for vector in vectors for value in vector))
        self.assertAlmostEqual(sum(value * value for value in query), 1.0, places=4)

    def test_persisted_counts_and_filtered_exact_search(self) -> None:
        self.assertEqual(self.store.count("A"), 543)
        self.assertEqual(self.store.count("B"), 289)
        query = self.embedder.embed_query(
            "Trong chương Modules, executable statements được chạy khi nào?"
        )
        hits = self.store.search(
            "B", query, top_k=3, filters={"chapter": "06_modules"}
        )
        self.assertEqual(len(hits), 3)
        self.assertTrue(all(hit["metadata"]["chapter"] == "06_modules" for hit in hits))
        self.assertGreaterEqual(hits[0]["score"], hits[1]["score"])
        self.assertGreaterEqual(hits[1]["score"], hits[2]["score"])
        with self.assertRaises(ValueError):
            self.store.search("B", query, filters={"gold_unit_id": "forbidden"})

    def test_reingest_removes_stale_chunks_in_scoped_strategy(self) -> None:
        chunks = [
            Chunk(
                chunk_id=f"CP3_TEST:{number}", document_id="cp3-test-doc",
                source="test", page=None, unit_id="test-unit", sequence=1,
                char_start=number, char_end=number + 1, text=text,
                metadata={"chapter": "test", "version": "test"},
            )
            for number, text in enumerate(("alpha", "beta"))
        ]
        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
        try:
            self.store.upsert("CP3_TEST", chunks, vectors)
            self.assertEqual(self.store.count("CP3_TEST"), 2)
            self.store.upsert("CP3_TEST", chunks[:1], vectors[:1])
            self.assertEqual(self.store.count("CP3_TEST"), 1)
        finally:
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM day06_chunks WHERE strategy = %s", ("CP3_TEST",)
                    )
        self.assertEqual(self.store.count("CP3_TEST"), 0)


if __name__ == "__main__":
    unittest.main()
