# Gold benchmark — CP1

`questions.json` contains 20 questions frozen before retrieval: 15 Dev and
5 Test. Every question has an expected answer, an evidence quote, the corpus
source path and a `gold_unit_id`. `gold_page` is `null` because the selected
plain-text corpus is non-paginated; `gold_unit_id` is the traceable equivalent
defined by `data/manifest.json`.

Four questions have a predeclared `chapter` filter, including two Test
questions. The filter is used only when the wording explicitly names a chapter;
it must never be inferred from gold metadata. `split_manifest.json` records the
frozen split, ten source positions for later coherence auditing, the Dev-only
strategy selection rule and SHA-256 locks for both questions and corpus
manifest.

Validate without running retrieval:

```powershell
starter\.venv\Scripts\python starter\scripts\validate_benchmark.py
```

Expected summary:

```text
Benchmark validated OK: 20 questions (15 Dev/5 Test), 4 filters (2 Test), 20/20 evidence verified, 10 coherence positions.
```

Do not run `--freeze` again after experiments begin. Any intentional benchmark
change invalidates the recorded digest and must be documented; Test retrieval
must remain unopened until Dev selection and strategy freeze in CP4.
