"""Download a reproducible, attributed Vietnamese Wikipedia corpus snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "vi_wikipedia_computing"
CATALOG_PATH = CORPUS_DIR / "source_catalog.json"
API_URL = "https://vi.wikipedia.org/w/api.php"
USER_AGENT = "Day06DataIngestionLab/1.0 (educational corpus; repository attribution)"
PAGES_PER_COLLECTION = 15
MIN_NORMALIZED_CHARS = 1_500
COLLECTIONS = {
    "ngon_ngu_lap_trinh": "Thể loại:Ngôn ngữ lập trình",
    "khoa_hoc_may_tinh": "Thể loại:Khoa học máy tính",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        normalized = re.sub(r"[ \t\f\v]+", " ", paragraph)
        normalized = re.sub(r" *\n *", "\n", normalized).strip()
        if normalized:
            paragraphs.append(normalized)
    return "\n\n".join(paragraphs)


def api(params: dict[str, str]) -> dict[str, object]:
    query = {
        "action": "query", "format": "json", "formatversion": "2", "maxlag": "5", **params
    }
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(query)}", headers={"User-Agent": USER_AGENT}
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 503} or attempt == 4:
                raise
            delay = int(exc.headers.get("Retry-After", 2 ** (attempt + 1)))
            time.sleep(min(delay, 30))
    raise RuntimeError("MediaWiki request retries exhausted")


def category_members(category: str) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    continuation: str | None = None
    while True:
        params = {
            "list": "categorymembers", "cmtitle": category, "cmnamespace": "0",
            "cmlimit": "500", "cmsort": "sortkey", "cmdir": "asc",
        }
        if continuation:
            params["cmcontinue"] = continuation
        payload = api(params)
        members.extend(payload["query"]["categorymembers"])
        continuation = payload.get("continue", {}).get("cmcontinue")
        if not continuation:
            return members


def page_details(pageids: list[int]) -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    for offset in range(0, len(pageids), 50):
        payload = api({
            "pageids": "|".join(str(value) for value in pageids[offset:offset + 50]),
            "prop": "info|revisions", "inprop": "url", "rvprop": "ids|timestamp",
        })
        pages.extend(payload["query"]["pages"])
    return pages


def download_article(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    content = soup.select_one(".mw-parser-output")
    if content is None:
        raise RuntimeError(f"Article content container is absent: {url}")
    for unwanted in content.select(
        "table, style, script, sup.reference, .reflist, .navbox, .vertical-navbox, "
        ".metadata, .mw-editsection, .noprint"
    ):
        unwanted.decompose()
    blocks = []
    for element in content.select("h2, h3, h4, p, li"):
        value = element.get_text(" ", strip=True)
        if value:
            blocks.append(value)
    return normalize_text("\n\n".join(blocks))


def safe_filename(pageid: int, title: str) -> str:
    slug = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()[:70] or "article"
    return f"{pageid}-{slug}.txt"


def build_snapshot() -> dict[str, object]:
    selected: list[dict[str, object]] = []
    used_pageids: set[int] = set()
    for collection, category in COLLECTIONS.items():
        members = category_members(category)
        details = page_details([int(item["pageid"]) for item in members])
        by_id = {int(item["pageid"]): item for item in details if "missing" not in item}
        accepted = []
        for member in members:
            pageid = int(member["pageid"])
            page = by_id.get(pageid)
            if not page or pageid in used_pageids:
                continue
            text = download_article(str(page["canonicalurl"]))
            if len(text) < MIN_NORMALIZED_CHARS:
                continue
            revision = page["revisions"][0]
            filename = safe_filename(pageid, str(page["title"]))
            accepted.append({
                "pageid": pageid, "title": page["title"], "collection": collection,
                "source_category": category, "canonical_url": page["canonicalurl"],
                "revision_id": revision["revid"], "revision_timestamp": revision["timestamp"],
                "retrieved_at": "2026-11-13",
                "path": f"data/vi_wikipedia_computing/{filename}",
                "normalized_character_count": len(text),
                "sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
                "text": text,
            })
            if len(accepted) == PAGES_PER_COLLECTION:
                break
        if len(accepted) != PAGES_PER_COLLECTION:
            raise RuntimeError(
                f"{category} yielded only {len(accepted)} pages with at least "
                f"{MIN_NORMALIZED_CHARS} normalized characters"
            )
        used_pageids.update(int(item["pageid"]) for item in accepted)
        selected.extend(accepted)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for item in selected:
        (ROOT / str(item["path"])).write_text(
            str(item.pop("text")) + "\n", encoding="utf-8", newline="\n"
        )
    return {
        "snapshot_version": 1, "created_at": "2026-11-13", "api": API_URL,
        "selection_rule": (
            "First 15 namespace-0 pages in MediaWiki category sort order with at least "
            "1,500 normalized characters; duplicate page IDs excluded across collections."
        ),
        "license": {
            "name": "Creative Commons Attribution-ShareAlike 4.0 International",
            "spdx": "CC-BY-SA-4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "attribution": (
                "Article title, canonical URL and revision ID are recorded per file. "
                "Wikipedia contributors are available through each linked revision history."
            ),
            "terms_url": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        },
        "collections": COLLECTIONS, "articles": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Replace the locked corpus snapshot")
    args = parser.parse_args()
    if CATALOG_PATH.exists() and not args.refresh:
        raise SystemExit(
            f"Snapshot already exists at {CATALOG_PATH}. Use --refresh only before benchmark creation."
        )
    snapshot = build_snapshot()
    CATALOG_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(
        f"Corpus snapshot OK: {len(snapshot['articles'])} Vietnamese articles, "
        f"{len(snapshot['collections'])} source categories."
    )


if __name__ == "__main__":
    main()
