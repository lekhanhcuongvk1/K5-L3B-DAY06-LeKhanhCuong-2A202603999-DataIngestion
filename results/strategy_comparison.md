# CP4 strategy comparison

## Integrity and selection

The benchmark and split were frozen before retrieval. All 15 Dev questions were
run for A/B/C first. Strategy **B** was selected and frozen at
`2026-11-13T21:04:12+07:00`, before the one-time Test run. C later scored higher
on Test Evidence Hit@3, but Test was not used to revise the selection or tune any
configuration.

## Retrieval results

| Strategy | Split | Hit@1 | Evidence Hit@3 | Mean retrieval time |
|---|---|---|---|---:|
| A | Dev | 3/15 | 7/15 | 43.033 ms |
| A | Test | 0/5 | 0/5 | 33.210 ms |
| B | Dev | 7/15 | 9/15 | 32.862 ms |
| B | Test | 1/5 | 2/5 | 32.809 ms |
| C | Dev | 7/15 | 9/15 | 27.754 ms |
| C | Test | 1/5 | 3/5 | 29.706 ms |

Timing is wall-clock time on this machine and is not a controlled performance
benchmark. C shares B's 289 stored chunks; it does not incur a separate embedding
or ingestion cost. The measured local embedding/API cost was USD 0.

## Five evaluation dimensions

| Strategy | Coherence mean /2 (n=10) | Metadata correct | Filter compliance | Grounding mean /2 (n=5) |
|---|---:|---:|---:|---:|
| A | 1.0 | 15/15 Test hits | N/A | 1.2 |
| B | 2.0 | 15/15 Test hits | N/A | 1.0 |
| C | 2.0 | 15/15 Test hits | 6/6 returned filtered hits | 1.4 |

Across all strategies, metadata was complete and correct for 45/45 returned Test
records. `unit_id` and character spans provide traceability for the non-paginated
corpus; `chapter` enables the predeclared filter. A limitation is that chapter
filtering only helps when the user/query context supplies a trustworthy chapter.

## Controlled comparisons

- **A–B (chunking):** B improved Dev Evidence Hit@3 from 7/15 to 9/15 and
  coherence from 1.0 to 2.0 while reducing stored chunks from 543 to 289. The
  fixed windows in A repeatedly ended mid-sentence or mid-token. B is therefore
  the selected strategy under the predeclared Dev rule.
- **B–C (filter only):** B and C use identical chunks, vectors, model, metric and
  store. They were identical on unfiltered queries. On Test, C recovered Q18's
  complete evidence at rank 3 through the declared chapter filter, increasing
  Evidence Hit@3 from 2/5 to 3/5. This is post-freeze analysis, not a reason to
  retroactively change the selected strategy.

## Failure examples

1. **Q04 — queue/deque, all strategies:** none of the top-3 results contained the
   `collections.deque` evidence. Results were distracted by generic language about
   alternatives and performance. This indicates cross-language semantic matching
   was insufficient for this wording, independent of chunk coherence.
2. **Q14 — file closing with `with`, all strategies:** retrieval found equivalent
   cleanup evidence in the Errors chapter, but the chunks omitted the preceding
   `with` subject. Official Evidence Hit@3 remains false because the frozen gold
   source/unit and full quote were not retrieved; grounding is only partial (1/2).
3. **Q18 — exact decimal/accounting:** B missed the complete recommendation, while
   C's predeclared chapter filter placed it at rank 3. A returned decisive fragments
   split at a fixed boundary, illustrating why official full-evidence retrieval and
   manual grounding can differ.

## Limitations

The Test set has only five questions, labels were reviewed by the author with
Codex assistance, and retrieval uses one multilingual local model on one corpus.
The results do not establish a generally superior strategy. No Test-dependent
tuning or rerun was performed.
