#!/usr/bin/env python3
"""
Build the expanded Krillion v1.2.0 database (500+ consecutive non-repeating days)
from:
  1. All 159 core curated & Wikidata-enriched prompts (deepened up to 8,000 answers)
  2. Fixed & broadened Wikidata master SPARQL datasets (TV, anime, manga, songs,
     video games + genres, movies by decade/genre/country, Americas/world cities with
     broadened P31 classes, rivers, mountains, sports, science, nature, history, foods)
  3. Batched Wikidata English skos:altLabel aliases merged cleanly across entries
  4. Letter-slices of large core & master Wikidata pools
  5. Rich English wordcraft prompts derived from /usr/share/dict/ + Norvig 333k frequencies

Outputs:
  - public/data/chunks/chunk-000.json .. chunk-255.json (256 deterministic chunks)
  - src/data/manifest.ts (PROMPT_MANIFEST, TOTAL_ANSWER_COUNT, YEAR_COVERAGE_DAYS, THEMED_PACKS)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
MASTER_CACHE = CACHE_DIR / "master_v2"
ALIASES_CACHE_PATH = CACHE_DIR / "aliases_en.json"
ENRICHED_159_DIR = CACHE_DIR / "enriched_159"
WORD_FREQ_PATH = CACHE_DIR / "word_freq.txt"
OLD_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
OUT_CHUNKS_DIR = ROOT / "public" / "data" / "chunks"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

NUM_CHUNKS = 256
TIERS = ["plankton", "tooclever", "schooler", "rare", "deepcut", "krillion"]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "KrillionStaticBuilder/1.3 (https://gitlab.com; static-pages-game)"
MIN_ANSWERS = 30
MAX_FACET_ANSWERS = 2500
MAX_SEED_ANSWERS = 8000
MAX_ALIASES_PER_ENTRY = 6


# Comprehensive curated island & island territory additions (ensuring Bonaire, Aruba,
# Curacao, Caribbean islands, British/European/Pacific/Asian islands are never missed)
CURATED_ISLANDS: list[tuple[str, float, list[str]]] = [
    ("Bonaire", 45.0, ["Bonaire Island"]),
    ("Aruba", 85.0, []),
    ("Curacao", 78.0, ["Curaçao"]),
    ("Sint Maarten", 55.0, ["Saint Martin"]),
    ("Saba", 24.0, ["Saba Island"]),
    ("Sint Eustatius", 22.0, ["Statia"]),
    ("Saint Lucia", 82.0, ["St Lucia", "St. Lucia"]),
    ("Saint Vincent", 58.0, ["St Vincent", "St. Vincent"]),
    ("Grenada", 80.0, []),
    ("Dominica", 76.0, []),
    ("Antigua", 64.0, []),
    ("Barbuda", 28.0, []),
    ("Saint Kitts", 50.0, ["St Kitts", "St. Kitts"]),
    ("Nevis", 26.0, []),
    ("Barbados", 92.0, []),
    ("Trinidad", 72.0, []),
    ("Tobago", 48.0, []),
    ("Anguilla", 46.0, []),
    ("Montserrat", 44.0, []),
    ("Guadeloupe", 68.0, []),
    ("Martinique", 69.0, []),
    ("Saint Barthelemy", 36.0, ["St Barts", "St. Barts", "Saint-Barthelemy"]),
    ("Bermuda", 88.0, []),
    ("Grand Cayman", 52.0, []),
    ("Cayman Brac", 18.0, []),
    ("Little Cayman", 14.0, []),
    ("Turks and Caicos", 56.0, []),
    ("Puerto Rico", 130.0, []),
    ("Vieques", 24.0, []),
    ("Culebra", 19.0, []),
    ("Hispaniola", 74.0, []),
    ("New Providence", 34.0, []),
    ("Grand Bahama", 32.0, []),
    ("Eleuthera", 21.0, []),
    ("Exuma", 20.0, []),
    ("Cozumel", 48.0, []),
    ("Roatan", 30.0, []),
    ("Margarita Island", 31.0, []),
    ("Isle of Wight", 64.0, []),
    ("Anglesey", 46.0, []),
    ("Isle of Mull", 32.0, ["Mull"]),
    ("Isle of Lewis", 31.0, ["Lewis"]),
    ("Gozo", 42.0, []),
    ("Elba", 52.0, []),
    ("Capri", 62.0, []),
    ("Ischia", 40.0, []),
    ("Rhodes", 72.0, []),
    ("Corfu", 68.0, []),
    ("Mykonos", 64.0, []),
    ("Naxos", 42.0, []),
    ("Paros", 38.0, []),
    ("Zakynthos", 41.0, []),
    ("Lesbos", 50.0, []),
    ("Menorca", 54.0, []),
    ("Formentera", 34.0, []),
    ("Tenerife", 76.0, []),
    ("Gran Canaria", 68.0, []),
    ("Lanzarote", 58.0, []),
    ("Fuerteventura", 49.0, []),
    ("La Palma", 46.0, []),
    ("Madeira", 78.0, []),
    ("Sao Miguel", 35.0, []),
    ("Terceira", 26.0, []),
    ("Pico", 22.0, []),
    ("Bioko", 32.0, []),
    ("Sao Tome", 44.0, []),
    ("Principe", 24.0, []),
    ("Pemba", 28.0, []),
    ("Mafia Island", 16.0, []),
    ("Nosy Be", 20.0, []),
    ("Rodrigues", 26.0, []),
    ("Mahe", 32.0, []),
    ("Praslin", 22.0, []),
    ("Bahrain", 96.0, []),
    ("Phuket", 74.0, []),
    ("Koh Samui", 48.0, []),
    ("Koh Phi Phi", 36.0, []),
    ("Penang", 66.0, []),
    ("Langkawi", 44.0, []),
    ("Singapore", 145.0, []),
    ("Bintan", 22.0, []),
    ("Batam", 28.0, []),
    ("Sulawesi", 68.0, []),
    ("Lombok", 52.0, []),
    ("Sumbawa", 34.0, []),
    ("Flores", 36.0, []),
    ("Komodo", 46.0, []),
    ("Timor", 58.0, []),
    ("Halmahera", 26.0, []),
    ("New Guinea", 86.0, []),
    ("Cebu", 62.0, []),
    ("Palawan", 54.0, []),
    ("Boracay", 45.0, []),
    ("Bohol", 42.0, []),
    ("Taiwan", 140.0, []),
    ("Hainan", 68.0, []),
    ("Hong Kong Island", 70.0, []),
    ("Jeju", 66.0, ["Jeju Island"]),
    ("Ulleungdo", 22.0, []),
    ("Shikoku", 72.0, []),
    ("Kyushu", 78.0, []),
    ("Okinawa", 84.0, []),
    ("Yakushima", 34.0, []),
    ("Sakhalin", 64.0, []),
    ("Kangaroo Island", 38.0, []),
    ("Fraser Island", 34.0, ["K'gari"]),
    ("Lord Howe Island", 24.0, []),
    ("Norfolk Island", 32.0, []),
    ("Christmas Island", 36.0, []),
    ("North Island", 72.0, []),
    ("South Island", 72.0, []),
    ("Stewart Island", 28.0, []),
    ("Waiheke", 20.0, ["Waiheke Island"]),
    ("Viti Levu", 36.0, []),
    ("Vanua Levu", 24.0, []),
    ("Upolu", 26.0, []),
    ("Savaii", 22.0, []),
    ("Tutuila", 20.0, []),
    ("Tongatapu", 24.0, []),
    ("Rarotonga", 30.0, []),
    ("Aitutaki", 18.0, []),
    ("Moorea", 32.0, []),
    ("Nauru", 64.0, []),
    ("Tuvalu", 60.0, []),
    ("Tarawa", 26.0, []),
    ("Majuro", 24.0, []),
    ("Guam", 82.0, []),
    ("Saipan", 46.0, []),
    ("Tinian", 26.0, []),
    ("Kauai", 56.0, []),
    ("Molokai", 36.0, []),
    ("Lanai", 30.0, []),
    ("Vancouver Island", 74.0, []),
    ("Newfoundland", 82.0, []),
    ("Prince Edward Island", 72.0, []),
    ("Cape Breton", 48.0, ["Cape Breton Island"]),
    ("Long Island", 86.0, []),
    ("Manhattan", 110.0, []),
    ("Staten Island", 74.0, []),
    ("Martha's Vineyard", 52.0, []),
    ("Nantucket", 50.0, []),
    ("Key West", 62.0, []),
    ("Catalina Island", 42.0, []),
    ("Alcatraz", 72.0, ["Alcatraz Island"]),
    ("Kodiak Island", 40.0, []),
    ("Galveston", 44.0, ["Galveston Island"]),
    ("Tierra del Fuego", 66.0, []),
    ("Chiloe", 38.0, ["Chiloe Island"]),
    ("Robinson Crusoe Island", 22.0, []),
    ("Isabela", 28.0, []),
]


def normalize_answer(raw: str) -> str:
    s = unicodedata.normalize("NFD", raw)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = s.replace("++", " plus plus").replace("#", " sharp").replace("&", " and ")
    s = re.sub(r"['’`]", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_article(norm: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", norm).strip()


def plural_variants(norm: str) -> list[str]:
    out = [norm]
    stripped = strip_article(norm)
    if stripped and stripped != norm:
        out.append(stripped)
    for form in list(out):
        if len(form) >= 4 and " " not in form:
            if form.endswith("s") and not form.endswith("ss"):
                out.append(form[:-1])
            elif not form.endswith("s"):
                out.append(f"{form}s")
            if form.endswith("es") and len(form) >= 5:
                out.append(form[:-2])
    return list(dict.fromkeys(out))


def clean_label(label: str) -> tuple[str, list[str]] | None:
    label = label.strip()
    if not label or re.match(r"^Q\d+$", label):
        return None
    if any(bad in label for bad in ["\n", "[", "]", "{", "}", "http://", "https://"]):
        return None
    lower = label.lower()
    if lower.startswith(("list of ", "category:", "template:", "wikipedia:", "portal:")):
        return None
    if len(label) > 52 or not re.search(r"[a-zA-Z]", label):
        return None
    aliases: list[str] = []
    m = re.match(r"^(.+?)\s*\([^)]{2,28}\)$", label)
    if m:
        short = m.group(1).strip()
        if len(short) >= 2:
            aliases.append(label)
            label = short
    return label, aliases


def clean_wikidata_aliases(
    canonical: str,
    raw_aliases: list[str],
    max_aliases: int = MAX_ALIASES_PER_ENTRY,
) -> list[str]:
    cnorm = normalize_answer(canonical)
    if not cnorm:
        return []
    canon_vars = set(plural_variants(cnorm))
    seen_norms: set[str] = set(canon_vars)
    accepted: list[str] = []

    def is_valid_alias(al: str) -> bool:
        al = al.strip()
        if len(al) < 2 or len(al) > 38:
            return False
        if any(ch in al for ch in (",", "(", ")", "[", "]", "{", "}", '"', "\n", "\r")):
            return False
        if "http://" in al or "https://" in al:
            return False
        if not re.search(r"[a-zA-Z]", al):
            return False
        lower = al.lower()
        if lower.startswith(("list of ", "category:", "template:", "wikipedia:", "portal:", "file:")):
            return False
        return True

    cleaned_candidates: list[str] = []
    for raw in raw_aliases:
        s = raw.strip()
        if is_valid_alias(s):
            cleaned_candidates.append(s)

    cleaned_candidates.sort(key=lambda s: (len(s) > 22, len(s), s.lower(), s))
    for al in cleaned_candidates:
        anorm = normalize_answer(al)
        if not anorm:
            continue
        avars = plural_variants(anorm)
        if any(v in seen_norms for v in avars):
            continue
        seen_norms.update(avars)
        accepted.append(al)
        if len(accepted) >= max_aliases:
            break
    return accepted


def first_alpha_letter(s: str) -> str | None:
    s = strip_article(normalize_answer(s))
    if not s:
        return None
    ch = s[0]
    return ch.upper() if "a" <= ch <= "z" else None


def post_sparql(query: str, timeout: int = 25) -> dict[str, Any]:
    body = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        SPARQL_ENDPOINT,
        data=body,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_sparql_rows(
    name: str,
    query: str,
    fallback_query: str | None = None,
) -> list[dict[str, str]]:
    MASTER_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = MASTER_CACHE / f"{name}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text("utf-8"))
        if len(data) > 0:
            return data

    queries_to_try = [query] + ([fallback_query] if fallback_query else [])
    for q_idx, active_query in enumerate(queries_to_try):
        for attempt, delay in enumerate([0.45, 1.5, 3.0]):
            try:
                time.sleep(delay)
                payload = post_sparql(active_query, timeout=25)
                rows: list[dict[str, str]] = []
                for b in payload.get("results", {}).get("bindings", []):
                    row = {k: v.get("value", "") for k, v in b.items()}
                    lbl = row.get("itemLabel", "")
                    if not lbl or re.match(r"^Q\d+$", lbl):
                        continue
                    item_uri = row.pop("item", "")
                    if item_uri:
                        qid = item_uri.rsplit("/", 1)[-1]
                        if re.match(r"^Q\d+$", qid):
                            row["qid"] = qid
                    rows.append(row)
                if rows:
                    cache_file.write_text(json.dumps(rows), encoding="utf-8")
                suffix = " (fallback)" if q_idx > 0 else ""
                print(f"  [SPARQL] {name}{suffix}: {len(rows)} rows")
                return rows
            except urllib.error.HTTPError as exc:
                print(f"  [SPARQL retry {attempt + 1}] {name}: HTTP {exc.code}")
                if exc.code == 429:
                    time.sleep(4.0 * (attempt + 1))
            except Exception as exc:
                print(f"  [SPARQL retry {attempt + 1}] {name}: {exc}")

    v1_cache = CACHE_DIR / "master" / f"{name}.json"
    if v1_cache.exists():
        v1_data = json.loads(v1_cache.read_text("utf-8"))
        if len(v1_data) > 0:
            print(f"  [SPARQL fallback v1 cache] {name}: {len(v1_data)} rows")
            return v1_data

    return []


def dedup_rows_by_qid(
    rows: list[dict[str, str]],
    keep_min_year: bool = False,
) -> list[dict[str, str]]:
    by_qid: dict[str, dict[str, str]] = {}
    passthrough: list[dict[str, str]] = []

    for row in rows:
        qid = row.get("qid")
        if not qid:
            passthrough.append(row)
            continue
        prev = by_qid.get(qid)
        if prev is None:
            by_qid[qid] = dict(row)
            continue
        prev_sl = float(prev.get("sitelinks", 1) or 1)
        cur_sl = float(row.get("sitelinks", 1) or 1)
        if cur_sl > prev_sl:
            prev["sitelinks"] = row.get("sitelinks", prev.get("sitelinks", "1"))
        if keep_min_year and row.get("year"):
            cur_year = row["year"]
            prev_year = prev.get("year", "")
            if not prev_year or (cur_year.isdigit() and prev_year.isdigit() and int(cur_year) < int(prev_year)):
                prev["year"] = cur_year

    return list(by_qid.values()) + passthrough


def fetch_wikidata_aliases(qids: set[str]) -> dict[str, list[str]]:
    ALIASES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    alias_cache: dict[str, list[str]] = {}
    if ALIASES_CACHE_PATH.exists():
        alias_cache = json.loads(ALIASES_CACHE_PATH.read_text("utf-8"))

    missing = sorted(q for q in qids if q and q not in alias_cache)
    if not missing:
        print(f"  [Aliases] Loaded {len(alias_cache):,} QIDs from cache (0 missing).")
        return alias_cache

    batch_size = 400
    total_batches = (len(missing) + batch_size - 1) // batch_size
    print(f"  [Aliases] Fetching English skos:altLabel for {len(missing):,} QIDs in {total_batches} batches...")

    for b_idx in range(total_batches):
        batch = missing[b_idx * batch_size : (b_idx + 1) * batch_size]
        vals = " ".join(f"wd:{q}" for q in batch)
        q = f"""
SELECT ?item ?alt WHERE {{
  VALUES ?item {{ {vals} }}
  ?item skos:altLabel ?alt .
  FILTER(LANG(?alt) = "en")
}}"""
        fetched: dict[str, list[str]] = {qid: [] for qid in batch}
        ok = False
        for attempt, delay in enumerate([0.45, 2.0, 5.0]):
            try:
                time.sleep(delay)
                payload = post_sparql(q, timeout=25)
                for b in payload.get("results", {}).get("bindings", []):
                    item_uri = b.get("item", {}).get("value", "")
                    alt_val = b.get("alt", {}).get("value", "").strip()
                    qid = item_uri.rsplit("/", 1)[-1]
                    if qid in fetched and alt_val:
                        fetched[qid].append(alt_val)
                ok = True
                break
            except urllib.error.HTTPError as exc:
                print(f"  [Aliases batch {b_idx + 1}/{total_batches} retry {attempt + 1}] HTTP {exc.code}")
                if exc.code == 429:
                    time.sleep(6.0 * (attempt + 1))
            except Exception as exc:
                print(f"  [Aliases batch {b_idx + 1}/{total_batches} retry {attempt + 1}] {exc}")

        if ok:
            for qid, als in fetched.items():
                alias_cache[qid] = list(dict.fromkeys(als))

        if (b_idx + 1) % 15 == 0 or (b_idx + 1) == total_batches:
            ALIASES_CACHE_PATH.write_text(json.dumps(alias_cache, separators=(",", ":")), encoding="utf-8")
            print(f"  [Aliases] Progress: batch {b_idx + 1}/{total_batches} ({len(alias_cache):,} QIDs cached)")

    return alias_cache


def rows_to_scored_items(
    rows: list[dict[str, str]],
    alias_map: dict[str, list[str]],
) -> list[tuple[str, float, list[str]]]:
    items: list[tuple[str, float, list[str]]] = []
    for r in rows:
        cleaned = clean_label(r["itemLabel"])
        if not cleaned:
            continue
        canon, base_aliases = cleaned
        sl = float(r.get("sitelinks", 1) or 1)
        qid = r.get("qid", "")
        raw_als = list(base_aliases)
        if qid and qid in alias_map:
            raw_als.extend(alias_map[qid])
        valid_als = clean_wikidata_aliases(canon, raw_als)
        items.append((canon, sl, valid_als))
    return items


def build_balanced_tiers(
    scored_items: list[tuple[str, float, list[str]]],
    max_answers: int = MAX_FACET_ANSWERS,
) -> dict[str, list[Any]] | None:
    coalesced: dict[str, tuple[str, float, list[str]]] = {}
    for canon, sc, aliases in scored_items:
        cnorm = normalize_answer(canon)
        if not cnorm:
            continue
        if cnorm not in coalesced:
            coalesced[cnorm] = (canon, sc, list(aliases))
        else:
            prev_canon, prev_sc, prev_aliases = coalesced[cnorm]
            best_canon = canon if sc > prev_sc else prev_canon
            best_sc = sc if sc > prev_sc else prev_sc
            merged_als = list(dict.fromkeys([*prev_aliases, *aliases]))
            coalesced[cnorm] = (best_canon, best_sc, merged_als)

    ordered = sorted(coalesced.values(), key=lambda x: x[1], reverse=True)
    seen_norms: set[str] = set()
    unique: list[tuple[str, float, list[str]]] = []

    for canon, sc, aliases in ordered:
        cnorm = normalize_answer(canon)
        if not cnorm:
            continue
        pvars = plural_variants(cnorm)
        if any(v in seen_norms for v in pvars):
            continue
        valid_aliases: list[str] = []
        new_vars = list(pvars)
        cleaned_als = clean_wikidata_aliases(canon, aliases)
        for al in cleaned_als:
            anorm = normalize_answer(al)
            if not anorm:
                continue
            avars = plural_variants(anorm)
            if any(v in seen_norms or v in new_vars for v in avars):
                continue
            valid_aliases.append(al)
            new_vars.extend(avars)
        seen_norms.update(new_vars)
        unique.append((canon, sc, valid_aliases))
        if len(unique) >= max_answers:
            break

    n = len(unique)
    if n < MIN_ANSWERS:
        return None

    cuts = [
        max(2, round(n * 0.06)),
        max(4, round(n * 0.16)),
        max(7, round(n * 0.32)),
        max(12, round(n * 0.56)),
        max(18, round(n * 0.82)),
        n,
    ]
    prev = 0
    for idx in range(5):
        remaining_tiers = 5 - idx
        cuts[idx] = max(prev + 2, min(cuts[idx], n - remaining_tiers * 2))
        prev = cuts[idx]
    cuts[5] = n

    ranges = [
        ("plankton", 0, cuts[0]),
        ("tooclever", cuts[0], cuts[1]),
        ("schooler", cuts[1], cuts[2]),
        ("rare", cuts[2], cuts[3]),
        ("deepcut", cuts[3], cuts[4]),
        ("krillion", cuts[4], cuts[5]),
    ]

    tiers_map: dict[str, list[Any]] = {t: [] for t in TIERS}
    for tier_name, start, end in ranges:
        for canon, _sc, aliases in unique[start:end]:
            if aliases:
                tiers_map[tier_name].append([canon, *aliases])
            else:
                tiers_map[tier_name].append(canon)

    if any(len(tiers_map[t]) == 0 for t in TIERS):
        return None
    return tiers_map


def merge_additional_into_tiers(
    base_tiers: dict[str, list[Any]],
    additions: list[tuple[str, float, list[str]]],
    max_total: int = MAX_SEED_ANSWERS,
) -> dict[str, list[Any]]:
    """Preserve base seed/enriched items at their tiers, and append new verified items + aliases."""
    tier_weight = {
        "plankton": 140.0,
        "tooclever": 80.0,
        "schooler": 50.0,
        "rare": 30.0,
        "deepcut": 15.0,
        "krillion": 5.0,
    }
    combined: list[tuple[str, float, list[str]]] = []
    for t in TIERS:
        for item in base_tiers[t]:
            if isinstance(item, str):
                combined.append((item, tier_weight[t], []))
            else:
                combined.append((item[0], tier_weight[t], item[1:]))
    combined.extend(additions)
    merged = build_balanced_tiers(combined, max_answers=max_total)
    return merged if merged else base_tiers


class PromptRegistry:
    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self.seen_texts: set[str] = set()

    def add(
        self,
        pid: str,
        text: str,
        category: str,
        tiers_map: dict[str, list[Any]] | None,
    ) -> bool:
        if not tiers_map:
            return False
        pid = re.sub(r"[^a-z0-9-]+", "-", pid.lower()).strip("-")
        if not pid or pid in self.by_id:
            return False
        tkey = text.strip().lower()
        if tkey in self.seen_texts:
            return False
        count = sum(len(v) for v in tiers_map.values())
        if count < MIN_ANSWERS or any(len(tiers_map[t]) == 0 for t in TIERS):
            return False

        obj = {
            "id": pid,
            "text": text.strip(),
            "category": category,
            "answerCount": count,
            "tiers": tiers_map,
        }
        self.prompts.append(obj)
        self.by_id[pid] = obj
        self.seen_texts.add(tkey)
        return True

    def upgrade(
        self,
        pid: str,
        additions: list[tuple[str, float, list[str]]],
        max_total: int = MAX_SEED_ANSWERS,
    ) -> None:
        existing = self.by_id.get(pid)
        if not existing or not additions:
            return
        new_tiers = merge_additional_into_tiers(existing["tiers"], additions, max_total)
        existing["tiers"] = new_tiers
        existing["answerCount"] = sum(len(v) for v in new_tiers.values())


def load_seed_and_existing(reg: PromptRegistry) -> None:
    seeds: list[dict[str, Any]] = json.loads(SEED_PATH.read_text("utf-8"))
    for seed in seeds:
        pid = seed["id"]
        cached_json_path = ENRICHED_159_DIR / f"{pid}.json"
        old_json_path = OLD_PROMPTS_DIR / f"{pid}.json"
        src_path = cached_json_path if cached_json_path.exists() else old_json_path
        if src_path.exists():
            raw = json.loads(src_path.read_text("utf-8"))
            tiers_map = raw["tiers"]
            total = sum(len(v) for v in tiers_map.values())
            if total > MAX_SEED_ANSWERS:
                scale = MAX_SEED_ANSWERS / total
                trimmed: dict[str, list[Any]] = {}
                for t in TIERS:
                    keep = max(4, round(len(tiers_map[t]) * scale))
                    trimmed[t] = tiers_map[t][:keep]
                tiers_map = trimmed
        else:
            tiers_map = {t: [] for t in TIERS}
            for ans in seed["answers"]:
                if ans.get("aliases"):
                    tiers_map[ans["tier"]].append([ans["canonical"], *ans["aliases"]])
                else:
                    tiers_map[ans["tier"]].append(ans["canonical"])

        reg.add(pid, seed["text"], seed["category"], tiers_map)


def label_q(where_body: str, min_sl: int, limit: int, extra_vars: str = "", distinct: bool = False) -> str:
    dist = "DISTINCT " if distinct else ""
    sel_vars = f"?item ?itemLabel {extra_vars} ?sitelinks".replace("  ", " ")
    return f"""
SELECT {dist}{sel_vars} WHERE {{
{where_body}
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
}} ORDER BY DESC(?sitelinks) LIMIT {limit}""".strip()


CONTINENTS = [
    ("eu", "Q46", "European", 8),
    ("as", "Q48", "Asian", 8),
    ("af", "Q15", "African", 5),
    ("oc", "Q55643", "Oceanian", 3),
]

AMERICAS_COUNTRIES = [
    ("usa", "Q30", "the United States", 6, "VALUES ?ct { wd:Q515 wd:Q1093829 wd:Q1549591 }", 5000),
    ("canada", "Q16", "Canada", 4, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q3957 }", 2500),
    ("mexico", "Q96", "Mexico", 6, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q20202352 wd:Q1852859 }", 2500),
    ("brazil", "Q155", "Brazil", 8, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q3184121 }", 3000),
    ("argentina", "Q414", "Argentina", 4, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q3957 }", 2000),
    ("colombia", "Q739", "Colombia", 4, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q2555896 }", 2000),
    ("peru", "Q419", "Peru", 4, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q3957 }", 1800),
    ("chile", "Q298", "Chile", 4, "VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q1840161 }", 1800),
]

RIVER_COUNTRIES = [
    ("usa", "Q30", "the United States", 6),
    ("russia", "Q159", "Russia", 6),
    ("canada", "Q16", "Canada", 5),
    ("brazil", "Q155", "Brazil", 5),
    ("china", "Q148", "China", 5),
    ("france", "Q142", "France", 5),
    ("germany", "Q183", "Germany", 5),
    ("uk", "Q145", "the United Kingdom", 5),
    ("australia", "Q408", "Australia", 4),
    ("india", "Q668", "India", 5),
]

FILM_DECADES = [
    ("1940s", 1940, 1949, 8),
    ("1950s", 1950, 1959, 12),
    ("1960s", 1960, 1969, 12),
    ("1970s", 1970, 1979, 12),
    ("1980s", 1980, 1989, 12),
    ("1990s", 1990, 1999, 14),
    ("2000s", 2000, 2009, 15),
    ("2010s", 2010, 2019, 15),
    ("2020s", 2020, 2025, 12),
]

FILM_GENRES = [
    ("action", "Q188473", "Action"),
    ("adventure", "Q319221", "Adventure"),
    ("comedy", "Q157443", "Comedy"),
    ("crime", "Q959790", "Crime"),
    ("documentary", "Q93204", "Documentary"),
    ("drama", "Q130232", "Drama"),
    ("fantasy", "Q157394", "Fantasy"),
    ("mystery", "Q1200678", "Mystery"),
    ("romance", "Q1054574", "Romance"),
    ("romcom", "Q860626", "Romantic Comedy"),
    ("thriller", "Q2484376", "Thriller"),
    ("war", "Q369747", "War"),
    ("biopic", "Q645928", "Biographical"),
    ("superhero", "Q1535153", "Superhero"),
    ("family", "Q1361932", "Family"),
]

FILM_COUNTRIES = [
    ("france", "Q142", "French"),
    ("japan", "Q17", "Japanese"),
    ("uk", "Q145", "British"),
    ("italy", "Q38", "Italian"),
    ("germany", "Q183", "German"),
    ("india", "Q668", "Indian"),
    ("korea", "Q884", "South Korean"),
    ("spain", "Q29", "Spanish"),
    ("canada", "Q16", "Canadian"),
    ("australia", "Q408", "Australian"),
    ("sweden", "Q34", "Swedish"),
    ("mexico", "Q96", "Mexican"),
    ("china", "Q148", "Chinese"),
    ("russia", "Q159", "Russian"),
    ("brazil", "Q155", "Brazilian"),
]

TV_COUNTRIES = [
    ("us", "Q30", "American"),
    ("uk", "Q145", "British"),
    ("jp", "Q17", "Japanese"),
    ("kr", "Q884", "South Korean"),
    ("ca", "Q16", "Canadian"),
]

MASTER_LISTS: list[tuple[str, str, int, int, str, str, str, str | None]] = [
    # (cache_key, where_body, min_sl, limit, pid, prompt_text, cat, fallback_where_or_minsl)
    ("books", "  ?item wdt:P31 wd:Q7725634 .", 12, 6500, "gen-book", "Name a famous book or novel", "general", None),
    ("actors", "  ?item wdt:P106 wd:Q33999 .", 28, 6000, "mov-actor", "Name a film or TV actor", "movies", None),
    ("painters", "  ?item wdt:P106 wd:Q1028181 .", 18, 4500, "gen-painter", "Name a famous painter or artist", "general", None),
    ("bands", "  VALUES ?bt { wd:Q215380 wd:Q5741069 }\n  ?item wdt:P31 ?bt .", 15, 6500, "gen-band", "Name a musical band or group", "general", None),
    ("singers", "  ?item wdt:P106 wd:Q177220 .", 26, 6000, "gen-singer", "Name a singer or vocalist", "general", None),
    ("albums", "  ?item wdt:P31 wd:Q482994 .", 12, 6000, "gen-album", "Name a studio album", "general", None),
    ("languages", "  ?item wdt:P31 wd:Q34770 .", 6, 3000, "gen-language", "Name a world language", "general", None),
    ("universities", "  ?item wdt:P31 wd:Q3918 .", 20, 4500, "gen-university", "Name a university or college", "general", None),
    ("museums", "  ?item wdt:P31 wd:Q33506 .", 12, 4000, "gen-museum", "Name a museum", "general", None),
    ("castles", "  ?item wdt:P31 wd:Q23413 .", 8, 4000, "gen-castle", "Name a castle or palace", "general", None),
    ("airlines", "  ?item wdt:P31 wd:Q46970 .", 8, 3000, "gen-airline", "Name an airline", "general", None),
    ("airports", "  ?item wdt:P31 wd:Q1248784 .", 14, 4500, "geo-airport", "Name an international airport", "geography", None),
    ("battles", "  ?item wdt:P31 wd:Q178561 .", 15, 4500, "gen-battle", "Name a historical battle", "general", None),
    ("wars", "  ?item wdt:P31 wd:Q198 .", 15, 4000, "gen-war", "Name a historical war or conflict", "general", None),
    ("dishes", "  { ?item wdt:P31 wd:Q746549 } UNION { ?item wdt:P279 wd:Q746549 } .", 5, 4500, "gen-dish", "Name a traditional dish or food", "general", None),
    ("football_clubs", "  ?item wdt:P31 wd:Q476028 .", 15, 5000, "spt-football-club", "Name a football (soccer) club", "sports", None),
    ("nba_players", "  ?item wdt:P106 wd:Q3665646 .", 16, 4500, "spt-nba-player", "Name a basketball player", "sports", None),
    ("baseball_players", "  ?item wdt:P106 wd:Q10871364 .", 12, 4000, "spt-mlb-player", "Name a baseball player", "sports", None),
    ("f1_drivers", "  ?item wdt:P106 wd:Q10841764 .", 10, 3000, "spt-f1-driver", "Name a Formula 1 driver", "sports", None),
    ("boxers", "  ?item wdt:P106 wd:Q11338576 .", 12, 4000, "spt-boxer", "Name a boxer", "sports", None),
    ("chess_players", "  ?item wdt:P106 wd:Q10873124 .", 10, 3500, "spt-chess-player", "Name a chess grandmaster or player", "sports", None),
    ("golfers_v2", "  ?item wdt:P106 wd:Q490253 .", 4, 2500, "spt-golfer", "Name a professional golfer", "sports", None),
    ("nfl_players", "  ?item wdt:P106 wd:Q19204627 .", 12, 4500, "spt-nfl-player", "Name an American football (NFL) player", "sports", None),
    ("nhl_players", "  ?item wdt:P106 wd:Q11774891 .", 12, 4500, "spt-nhl-player", "Name an ice hockey (NHL) player", "sports", None),
    ("swimmers", "  ?item wdt:P106 wd:Q10843402 .", 10, 3500, "spt-swimmer", "Name a competitive swimmer", "sports", None),
    ("cyclists", "  ?item wdt:P106 wd:Q2309784 .", 12, 4500, "spt-cyclist", "Name a professional cyclist", "sports", None),
    ("cricketers", "  ?item wdt:P106 wd:Q12299841 .", 10, 4000, "spt-cricketer", "Name a cricketer", "sports", None),
    ("philosophers", "  ?item wdt:P106 wd:Q4964182 .", 16, 4000, "gen-philosopher", "Name a philosopher", "general", None),
    ("architects", "  ?item wdt:P106 wd:Q42973 .", 12, 4000, "gen-architect", "Name a famous architect", "general", None),
    ("inventors", "  ?item wdt:P106 wd:Q205375 .", 12, 4000, "gen-inventor", "Name an inventor", "general", None),
    ("explorers", "  ?item wdt:P106 wd:Q11900058 .", 10, 3000, "gen-explorer", "Name a famous explorer", "general", None),
    ("monarchs", "  { ?item wdt:P39 wd:Q116 } UNION { ?item wdt:P106 wd:Q116 } .", 12, 3000, "gen-monarch", "Name a monarch, king, or queen", "general", None),
    ("companies", "  ?item wdt:P31 wd:Q4830453 .", 22, 5000, "gen-company", "Name a well-known company or corporation", "general", None),
    ("websites", "  ?item wdt:P31 wd:Q35127 .", 12, 4000, "gen-website", "Name a website or online platform", "general", None),
    ("spacecraft", "  { ?item wdt:P31 wd:Q40218 } UNION { ?item wdt:P31 wd:Q26529 } .", 5, 2500, "gen-spacecraft", "Name a spacecraft or space probe", "general", None),
    ("stars", "  ?item wdt:P31 wd:Q523 .", 18, 3000, "gen-star", "Name a star in the night sky", "general", None),
    ("compounds", "  ?item wdt:P31 wd:Q113145171 .", 26, 4000, "gen-compound", "Name a chemical compound or molecule", "general", "28"),
    ("diseases", "  { ?item wdt:P31 wd:Q12136 } UNION { ?item wdt:P31 wd:Q112193867 } .", 8, 4000, "gen-disease", "Name a medical disease or condition", "general", "14"),
    ("cat_breeds", "  ?item wdt:P31 wd:Q43577 .", 1, 1500, "gen-cat-breed", "Name a cat breed", "general", None),
    ("horse_breeds", "  ?item wdt:P31 wd:Q23002039 .", 1, 1800, "gen-horse-breed", "Name a horse breed", "general", None),
    ("breads", "  { ?item wdt:P31 wd:Q7802 } UNION { ?item wdt:P279 wd:Q7802 } .", 1, 2000, "gen-bread", "Name a type of bread", "general", None),
    ("soups", "  { ?item wdt:P31 wd:Q41415 } UNION { ?item wdt:P279 wd:Q41415 } .", 1, 2000, "gen-soup", "Name a soup or stew", "general", None),
    ("sauces", "  { ?item wdt:P31 wd:Q178359 } UNION { ?item wdt:P279 wd:Q178359 } .", 1, 2000, "gen-sauce", "Name a sauce or condiment", "general", None),
    ("pastries", "  { ?item wdt:P31 wd:Q477248 } UNION { ?item wdt:P279 wd:Q477248 } .", 1, 2000, "gen-pastry", "Name a pastry or baked sweet", "general", None),
    ("wine_grapes", "  ?item wdt:P31 wd:Q958314 .", 1, 1500, "gen-grape", "Name a wine grape variety", "general", None),
    ("comics_chars", "  ?item wdt:P31 wd:Q1114461 .", 6, 4000, "gen-comic-char", "Name a comic book character", "general", None),
    ("skyscrapers", "  ?item wdt:P31 wd:Q11303 .", 6, 3500, "geo-skyscraper", "Name a skyscraper or tall tower", "geography", None),
    ("glaciers", "  ?item wdt:P31 wd:Q35666 .", 3, 2500, "geo-glacier", "Name a glacier", "geography", None),
    ("caves", "  ?item wdt:P31 wd:Q35509 .", 4, 2500, "geo-cave", "Name a cave or cavern", "geography", None),
    ("canyons", "  ?item wdt:P31 wd:Q150784 .", 2, 1800, "geo-canyon", "Name a canyon or gorge", "geography", None),
    ("bays", "  ?item wdt:P31 wd:Q39594 .", 4, 2500, "geo-bay", "Name a bay or gulf", "geography", None),
    ("capes", "  ?item wdt:P31 wd:Q185113 .", 4, 2500, "geo-cape", "Name a cape or headland", "geography", None),
    (
        "nobel_laureates",
        "  VALUES ?award { wd:Q38104 wd:Q44585 wd:Q80061 wd:Q37922 wd:Q35637 wd:Q47170 }\n  ?item wdt:P166 ?award .",
        5,
        2000,
        "gen-nobel",
        "Name a Nobel Prize laureate",
        "general",
        None,
    ),
]

SEED_DEEPEN_QUERIES: list[tuple[str, str, int, int, str]] = [
    ("rivers_world", "  ?item wdt:P31 wd:Q4022 .", 7, 7000, "geo-river"),
    ("lakes_world", "  ?item wdt:P31 wd:Q23397 .", 7, 6000, "geo-lake"),
    ("mountain_ranges_world", "  ?item wdt:P31 wd:Q46831 .", 3, 4000, "geo-mountain-range"),
    ("national_parks_world", "  ?item wdt:P31 wd:Q46169 .", 3, 4500, "geo-national-park"),
    ("landmarks_world", "  { ?item wdt:P1435 wd:Q9259 } UNION { ?item wdt:P31 wd:Q4989906 } .", 18, 5000, "geo-landmark"),
    ("waterfalls_world", "  ?item wdt:P31 wd:Q34038 .", 1, 3000, "geo-waterfall"),
    ("deserts_world", "  ?item wdt:P31 wd:Q8514 .", 1, 2000, "geo-desert"),
    ("volcanoes_world", "  ?item wdt:P31 wd:Q8072 .", 4, 4000, "gen-volcano"),
    ("bridges_world", "  ?item wdt:P31 wd:Q12280 .", 5, 4000, "gen-bridge"),
    ("stadiums_world", "  ?item wdt:P31 wd:Q483110 .", 6, 5000, "spt-stadium"),
    ("films_scifi_deep", "  ?item wdt:P31 wd:Q11424 .\n  ?item wdt:P136 wd:Q471839 .", 6, 5000, "mov-scifi-classic"),
    ("films_horror_deep", "  ?item wdt:P31 wd:Q11424 .\n  ?item wdt:P136 wd:Q200092 .", 6, 5000, "mov-horror"),
    ("directors_deep", "  ?item wdt:P106 wd:Q2526255 .", 25, 5000, "mov-director"),
    ("composers_deep", "  ?item wdt:P106 wd:Q36834 .", 12, 5000, "gen-composer"),
    ("scientists_deep", "  VALUES ?occ { wd:Q901 wd:Q169470 wd:Q593644 }\n  ?item wdt:P106 ?occ .", 20, 5000, "gen-scientist"),
    ("paintings_deep", "  ?item wdt:P31 wd:Q3305213 .", 5, 5000, "gen-painting"),
    ("music_genres_deep", "  ?item wdt:P31 wd:Q188451 .", 2, 4000, "gen-music-genre"),
    ("board_games_deep", "  ?item wdt:P31 wd:Q131436 .", 1, 4000, "gen-board-game"),
    ("superheroes_deep", "  { ?item wdt:P31 wd:Q188784 } UNION { ?item wdt:P106 wd:Q188784 } .", 1, 3500, "gen-superhero"),
]

PEOPLE_COUNTRY_QUERIES = [
    ("authors_country", "Q36180", "P106", "P27", 30, "gen-author-nat", "Name an author from {G}", "general"),
    ("bands_country", "Q215380", "P31", "P495", 14, "gen-band-nat", "Name a band from {G}", "general"),
    ("clubs_country", "Q476028", "P31", "P17", 12, "spt-club-nat", "Name a football club in {G}", "sports"),
    ("stadiums_country", "Q483110", "P31", "P17", 6, "spt-stad-nat", "Name a sports stadium in {G}", "sports"),
    ("islands_country", "Q23442", "P31", "P17", 6, "geo-isl-nat", "Name an island in {G}", "geography"),
    ("lakes_country", "Q23397", "P31", "P17", 6, "geo-lak-nat", "Name a lake in {G}", "geography"),
    ("parks_country", "Q46169", "P31", "P17", 3, "geo-prk-nat", "Name a national park in {G}", "geography"),
    ("unesco_country", "Q9259", "P1435", "P17", 4, "geo-her-nat", "Name a World Heritage Site in {G}", "geography"),
    ("dishes_country", "Q746549", "P31", "P495", 2, "gen-dish-nat", "Name a traditional food or dish from {G}", "general"),
    ("universities_country", "Q3918", "P31", "P17", 15, "gen-uni-nat", "Name a university in {G}", "general"),
    ("museums_country", "Q33506", "P31", "P17", 8, "gen-mus-nat", "Name a museum in {G}", "general"),
    ("castles_country", "Q23413", "P31", "P17", 5, "gen-cas-nat", "Name a castle or palace in {G}", "general"),
]


def fetch_all_master_v2_queries() -> dict[str, list[dict[str, str]]]:
    datasets: dict[str, list[dict[str, str]]] = {}

    # 1. Islands & archipelagos (broadened P31 + volcanic_islands fixed to Q1161185)
    island_queries = [
        ("islands_main", "Q23442", 8, 7000),
        ("island_countries", "Q112099", 1, 1200),
        ("atolls", "Q42523", 1, 1500),
        ("volcanic_islands", "Q1161185", 1, 1500),
        ("caribbean_public", "Q3237519", 1, 100),
        ("island_groups", "Q1402592", 1, 1500),
        ("archipelagos_broad", "Q33837", 2, 2500),
    ]
    for name, qid, min_sl, lim in island_queries:
        q = label_q(f"  ?item wdt:P31 wd:{qid} .", min_sl, lim)
        datasets[name] = dedup_rows_by_qid(run_sparql_rows(name, q))

    # 2. Cities by continent, country, Americas, US states, Australia
    for code, qid, _cname, min_sl in CONTINENTS:
        if code in {"eu", "af"}:
            eff_sl = 12 if code == "eu" else 6
            lim = 4500 if code == "eu" else 3500
            q = f"""
SELECT ?item ?itemLabel ?countryLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {eff_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  ?country rdfs:label ?countryLabel . FILTER(LANG(?countryLabel) = "en")
}} ORDER BY DESC(?sitelinks) LIMIT {lim}""".strip()
        else:
            q = f"""
SELECT DISTINCT ?item ?itemLabel ?countryLabel ?sitelinks WHERE {{
  VALUES ?ct {{ wd:Q515 wd:Q1549591 wd:Q51929311 }}
  ?item wdt:P31 ?ct .
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  ?country rdfs:label ?countryLabel . FILTER(LANG(?countryLabel) = "en")
}} ORDER BY DESC(?sitelinks) LIMIT 5000""".strip()
        datasets[f"cities_{code}"] = dedup_rows_by_qid(run_sparql_rows(f"cities_{code}", q))

    for code, qid, _cname, min_sl, ct_vals, lim in AMERICAS_COUNTRIES:
        q = label_q(f"  {ct_vals}\n  ?item wdt:P31 ?ct .\n  ?item wdt:P17 wd:{qid} .", min_sl, lim, distinct=True)
        datasets[f"cities_am_{code}"] = dedup_rows_by_qid(run_sparql_rows(f"cities_am_{code}", q))

    aus_city_q = label_q(
        "  VALUES ?ct { wd:Q515 wd:Q1549591 wd:Q3957 }\n  ?item wdt:P31 ?ct .\n  ?item wdt:P17 wd:Q408 .",
        3,
        2500,
        distinct=True,
    )
    datasets["cities_australia_broad"] = dedup_rows_by_qid(run_sparql_rows("cities_australia_broad", aus_city_q))

    us_states_q = """
SELECT ?item ?itemLabel ?stateLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q1093829 .
  ?item wdt:P131 ?state .
  ?state wdt:P31 wd:Q35657 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  ?state rdfs:label ?stateLabel . FILTER(LANG(?stateLabel) = "en")
} ORDER BY DESC(?sitelinks) LIMIT 6000""".strip()
    datasets["us_cities_by_state"] = dedup_rows_by_qid(run_sparql_rows("us_cities_by_state", us_states_q))

    # 3. Rivers by country
    for code, qid, _cname, min_sl in RIVER_COUNTRIES:
        q = label_q(f"  ?item wdt:P31 wd:Q4022 .\n  ?item wdt:P17 wd:{qid} .", min_sl, 2000)
        datasets[f"rivers_{code}"] = dedup_rows_by_qid(run_sparql_rows(f"rivers_{code}", q))

    # 4. Mountains world (new deep pool)
    mountains_q = label_q("  ?item wdt:P31 wd:Q8502 .", 10, 6000)
    datasets["mountains_world"] = dedup_rows_by_qid(run_sparql_rows("mountains_world", mountains_q))

    # 5. Films by decade (now includes 1950s!), genre, and country
    for dlabel, y0, y1, min_sl in FILM_DECADES:
        q = f"""
SELECT ?item ?itemLabel (YEAR(?pub) AS ?year) ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P577 ?pub .
  FILTER(?pub >= "{y0}-01-01T00:00:00Z"^^xsd:dateTime && ?pub < "{y1 + 1}-01-01T00:00:00Z"^^xsd:dateTime)
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
}} ORDER BY DESC(?sitelinks) LIMIT 4000""".strip()
        datasets[f"films_{dlabel}"] = dedup_rows_by_qid(
            run_sparql_rows(f"films_{dlabel}", q), keep_min_year=True
        )

    for gid, qid, _gname in FILM_GENRES:
        q = label_q(f"  ?item wdt:P31 wd:Q11424 .\n  ?item wdt:P136 wd:{qid} .", 8, 4000)
        datasets[f"film_genre_{gid}"] = dedup_rows_by_qid(run_sparql_rows(f"film_genre_{gid}", q))

    for cid, qid, _adj in FILM_COUNTRIES:
        q = label_q(f"  ?item wdt:P31 wd:Q11424 .\n  ?item wdt:P495 wd:{qid} .", 8, 3000)
        datasets[f"film_country_{cid}"] = dedup_rows_by_qid(run_sparql_rows(f"film_country_{cid}", q))

    # 6. TV series, Anime, Manga, Hit songs, Video games + genres
    datasets["tv_series_v2"] = dedup_rows_by_qid(
        run_sparql_rows("tv_series_v2", label_q("  ?item wdt:P31 wd:Q5398426 .", 10, 6500))
    )
    for code, qid, _adj in TV_COUNTRIES:
        q = label_q(f"  ?item wdt:P31 wd:Q5398426 .\n  ?item wdt:P495 wd:{qid} .", 8, 3000)
        datasets[f"tv_{code}"] = dedup_rows_by_qid(run_sparql_rows(f"tv_{code}", q))

    datasets["anime_series"] = dedup_rows_by_qid(
        run_sparql_rows("anime_series", label_q("  ?item wdt:P31 wd:Q63952888 .", 5, 4000))
    )
    datasets["manga_series"] = dedup_rows_by_qid(
        run_sparql_rows("manga_series", label_q("  ?item wdt:P31 wd:Q21198342 .", 5, 4000))
    )
    datasets["hit_songs"] = dedup_rows_by_qid(
        run_sparql_rows(
            "hit_songs",
            label_q("  VALUES ?st { wd:Q134556 wd:Q7366 }\n  ?item wdt:P31 ?st .", 16, 6500, distinct=True),
        )
    )
    datasets["video_games"] = dedup_rows_by_qid(
        run_sparql_rows("video_games", label_q("  ?item wdt:P31 wd:Q7889 .", 12, 6500))
    )

    vg_genre_queries = [
        ("rpg", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136 wd:Q744038 .", 8, 2500),
        ("fps", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136 wd:Q185029 .", 8, 2500),
        ("platformer", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136 wd:Q828322 .", 8, 2500),
        ("strategy", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136/wdt:P279* wd:Q472055 .", 6, 2500),
        ("racing", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136 wd:Q860750 .", 8, 2500),
        ("fighting", "  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P136 wd:Q343568 .", 8, 2500),
        ("horror", "  ?item wdt:P31 wd:Q7889 .\n  { ?item wdt:P136 wd:Q333967 } UNION { ?item wdt:P136 wd:Q11338014 } .", 4, 2000),
    ]
    for gid, where_b, min_sl, lim in vg_genre_queries:
        datasets[f"vg_genre_{gid}"] = dedup_rows_by_qid(
            run_sparql_rows(f"vg_genre_{gid}", label_q(where_b, min_sl, lim, distinct=True))
        )

    # 7. Master lists + broadened open seed deepening queries
    for key, where_b, min_sl, lim, _pid, _ptext, _cat, fb_sl in MASTER_LISTS:
        q = label_q(where_b, min_sl, lim, distinct=("VALUES" in where_b or "UNION" in where_b))
        fb_q = (
            label_q(where_b, int(fb_sl), lim, distinct=("VALUES" in where_b or "UNION" in where_b))
            if fb_sl
            else None
        )
        datasets[key] = dedup_rows_by_qid(run_sparql_rows(key, q, fb_q))

    for key, where_b, min_sl, lim, _pid in SEED_DEEPEN_QUERIES:
        q = label_q(where_b, min_sl, lim, distinct=("VALUES" in where_b or "UNION" in where_b))
        datasets[key] = dedup_rows_by_qid(run_sparql_rows(key, q))

    # 8. Footballers & animal species (fixed fishes_en!)
    datasets["footballers_v2"] = dedup_rows_by_qid(
        run_sparql_rows("footballers_v2", label_q("  ?item wdt:P106 wd:Q937857 .", 38, 6000))
    )

    animal_specs = [
        ("mammals_en", "Q7377", 25, 2500, False),
        ("birds_en", "Q5113", 25, 2500, False),
        ("reptiles_en", "Q10811", 22, 2500, False),
        ("fishes_en", "{ ?item wdt:P171* wd:Q127282 } UNION { ?item wdt:P171* wd:Q25371 } .", 15, 2500, True),
    ]
    for key, clade, min_sl, lim, is_custom in animal_specs:
        if is_custom:
            where_b = f"  ?item wdt:P105 wd:Q7432 .\n  {clade}"
            q = label_q(where_b, min_sl, lim, distinct=True)
        else:
            where_b = f'  ?item wdt:P1843 ?common .\n  FILTER(LANG(?common) = "en")\n  ?item wdt:P105 wd:Q7432 .\n  ?item wdt:P171* wd:{clade} .'
            q = label_q(where_b, min_sl, lim, distinct=True)
        datasets[key] = dedup_rows_by_qid(run_sparql_rows(key, q))

    # 9. People & places by country
    for key, qid, prop, grp_prop, min_sl, _id_pref, _fmt, _cat in PEOPLE_COUNTRY_QUERIES:
        q = f"""
SELECT DISTINCT ?item ?itemLabel ?grpLabel ?sitelinks WHERE {{
  ?item wdt:{prop} wd:{qid} .
  ?item wdt:{grp_prop} ?grp .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  ?grp rdfs:label ?grpLabel . FILTER(LANG(?grpLabel) = "en")
}} ORDER BY DESC(?sitelinks) LIMIT 5000""".strip()
        datasets[key] = dedup_rows_by_qid(run_sparql_rows(key, q))

    return datasets


def deepen_islands_and_archipelagos(
    reg: PromptRegistry,
    datasets: dict[str, list[dict[str, str]]],
    alias_map: dict[str, list[str]],
) -> None:
    """Ensure Bonaire, Aruba, Curacao, island countries, atolls, volcanic islands, and Caribbean entities are all included."""
    extra_islands: list[tuple[str, float, list[str]]] = list(CURATED_ISLANDS)
    for name in [
        "islands_main",
        "island_countries",
        "atolls",
        "volcanic_islands",
        "caribbean_public",
        "island_groups",
        "archipelagos_broad",
    ]:
        extra_islands.extend(rows_to_scored_items(datasets.get(name, []), alias_map))

    reg.upgrade("geo-island", extra_islands, MAX_SEED_ANSWERS)
    reg.upgrade("geo-archipelago", extra_islands, MAX_SEED_ANSWERS)


def slice_existing_prompts(reg: PromptRegistry) -> int:
    added = 0
    slice_configs = [
        ("gen-magazine", "Name a magazine starting with the letter {L}", "general"),
        ("gen-dinosaur", "Name a dinosaur starting with the letter {L}", "general"),
        ("gen-composer", "Name a classical composer starting with the letter {L}", "general"),
        ("gen-painting", "Name a famous painting starting with the letter {L}", "general"),
        ("gen-music-genre", "Name a music genre starting with the letter {L}", "general"),
        ("gen-car-brand", "Name a car brand starting with the letter {L}", "general"),
        ("gen-board-game", "Name a board game starting with the letter {L}", "general"),
        ("gen-dog-breed", "Name a dog breed starting with the letter {L}", "general"),
        ("gen-programming-lang", "Name a programming language starting with the letter {L}", "general"),
        ("gen-scientist", "Name a famous scientist starting with the letter {L}", "general"),
        ("gen-card-game", "Name a card game starting with the letter {L}", "general"),
        ("gen-volcano", "Name a volcano starting with the letter {L}", "general"),
        ("gen-mythical", "Name a mythical creature starting with the letter {L}", "general"),
        ("gen-boat", "Name a type of boat or ship starting with the letter {L}", "general"),
        ("gen-superhero", "Name a superhero starting with the letter {L}", "general"),
        ("mov-scifi-classic", "Name a sci-fi movie starting with the letter {L}", "movies"),
        ("mov-horror", "Name a horror movie starting with the letter {L}", "movies"),
        ("mov-western", "Name a Western movie starting with the letter {L}", "movies"),
        ("mov-musical", "Name a movie musical starting with the letter {L}", "movies"),
        ("mov-director", "Name a film director starting with the letter {L}", "movies"),
        ("mov-film-composer", "Name a film composer starting with the letter {L}", "movies"),
        ("mov-silent", "Name a silent film starting with the letter {L}", "movies"),
        ("spt-stadium", "Name a sports stadium starting with the letter {L}", "sports"),
        ("spt-olympian", "Name an Olympic gold medalist starting with the letter {L}", "sports"),
        ("spt-grand-slam-tennis", "Name a tennis champion starting with the letter {L}", "sports"),
        ("spt-cycling", "Name a cycling race starting with the letter {L}", "sports"),
        ("geo-river", "Name a river starting with the letter {L}", "geography"),
        ("geo-island", "Name an island starting with the letter {L}", "geography"),
        ("geo-mountain-range", "Name a mountain range starting with the letter {L}", "geography"),
        ("geo-mountain", "Name a mountain or peak starting with the letter {L}", "geography"),
        ("geo-national-park", "Name a national park starting with the letter {L}", "geography"),
        ("geo-lake", "Name a lake starting with the letter {L}", "geography"),
        ("geo-strait-canal", "Name a strait or canal starting with the letter {L}", "geography"),
        ("geo-peninsula", "Name a peninsula starting with the letter {L}", "geography"),
        ("geo-waterfall", "Name a waterfall starting with the letter {L}", "geography"),
        ("geo-desert", "Name a desert starting with the letter {L}", "geography"),
        ("geo-landmark", "Name a world landmark starting with the letter {L}", "geography"),
        ("geo-archipelago", "Name an island nation or archipelago starting with the letter {L}", "geography"),
        ("gen-tv-us", "Name an American TV show starting with the letter {L}", "general"),
    ]

    tier_weight = {
        "plankton": 100.0,
        "tooclever": 60.0,
        "schooler": 35.0,
        "rare": 18.0,
        "deepcut": 8.0,
        "krillion": 2.0,
    }

    for src_id, template, cat in slice_configs:
        src = reg.by_id.get(src_id)
        if not src:
            continue
        by_letter: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
        for t in TIERS:
            for item in src["tiers"][t]:
                if isinstance(item, str):
                    canon, aliases = item, []
                else:
                    canon, aliases = item[0], item[1:]
                ltr = first_alpha_letter(canon)
                if ltr:
                    by_letter[ltr].append((canon, tier_weight[t], aliases))

        for ltr, items in sorted(by_letter.items()):
            if len(items) < MIN_ANSWERS:
                continue
            pid = f"{src_id}-ltr-{ltr.lower()}"
            if reg.add(pid, template.format(L=ltr), cat, build_balanced_tiers(items)):
                added += 1
    return added


def assemble_master_prompts(
    reg: PromptRegistry,
    datasets: dict[str, list[dict[str, str]]],
    alias_map: dict[str, list[str]],
) -> int:
    added = 0

    def add_group_slices(
        rows: list[dict[str, str]],
        group_key: str,
        id_prefix: str,
        prompt_fmt: str,
        category: str,
        min_group: int = MIN_ANSWERS + 4,
    ) -> None:
        nonlocal added
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            grp = r.get(group_key, "").strip()
            if not grp or re.match(r"^Q\d+$", grp):
                continue
            buckets[grp].append(r)

        for grp, grp_rows in sorted(buckets.items()):
            items = rows_to_scored_items(grp_rows, alias_map)
            if len(items) < min_group:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", grp.lower()).strip("-")
            if reg.add(
                f"{id_prefix}-{slug}",
                prompt_fmt.format(G=grp),
                category,
                build_balanced_tiers(items),
            ):
                added += 1

    def add_letter_slices(
        rows: list[dict[str, str]],
        id_prefix: str,
        prompt_fmt: str,
        category: str,
    ) -> None:
        nonlocal added
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            cleaned = clean_label(r["itemLabel"])
            if not cleaned:
                continue
            ltr = first_alpha_letter(cleaned[0])
            if ltr:
                buckets[ltr].append(r)
        for ltr, ltr_rows in sorted(buckets.items()):
            items = rows_to_scored_items(ltr_rows, alias_map)
            if len(items) < MIN_ANSWERS:
                continue
            if reg.add(
                f"{id_prefix}-ltr-{ltr.lower()}",
                prompt_fmt.format(L=ltr),
                category,
                build_balanced_tiers(items),
            ):
                added += 1

    # 1. Cities by continent, Americas, South America, Australia, Canada, US states
    all_cities: list[dict[str, str]] = []
    for code, _qid, cname, _min_sl in CONTINENTS:
        rows = datasets.get(f"cities_{code}", [])
        all_cities.extend(rows)
        add_group_slices(rows, "countryLabel", f"geo-city-{code}", "Name a city in {G}", "geography")
        add_letter_slices(rows, f"geo-city-{code}", f"Name a {cname} city starting with the letter {{L}}", "geography")

    sa_combined_items: list[tuple[str, float, list[str]]] = []
    sa_codes = {"brazil", "argentina", "colombia", "peru", "chile"}
    for code, _qid, cname, _min_sl, _ct, _lim in AMERICAS_COUNTRIES:
        rows = datasets.get(f"cities_am_{code}", [])
        all_cities.extend(rows)
        items = rows_to_scored_items(rows, alias_map)
        if code in sa_codes:
            sa_combined_items.extend(items)
        if reg.add(f"geo-city-am-{code}", f"Name a city in {cname}", "geography", build_balanced_tiers(items, MAX_SEED_ANSWERS)):
            added += 1
        add_letter_slices(rows, f"geo-city-am-{code}", f"Name a city in {cname} starting with the letter {{L}}", "geography")

    reg.upgrade("geo-south-america-city", sa_combined_items, MAX_SEED_ANSWERS)
    reg.upgrade("geo-canada-city", rows_to_scored_items(datasets.get("cities_am_canada", []), alias_map), MAX_SEED_ANSWERS)
    reg.upgrade("geo-australia-city", rows_to_scored_items(datasets.get("cities_australia_broad", []), alias_map), MAX_SEED_ANSWERS)

    us_cities = datasets.get("us_cities_by_state", [])
    add_group_slices(us_cities, "stateLabel", "geo-us-city", "Name a city in {G}", "geography")
    add_letter_slices(all_cities, "geo-world-city", "Name a world city starting with the letter {L}", "geography")

    # 2. Rivers & mountains
    for code, _qid, cname, _min_sl in RIVER_COUNTRIES:
        rows = datasets.get(f"rivers_{code}", [])
        items = rows_to_scored_items(rows, alias_map)
        if reg.add(f"geo-riv-{code}", f"Name a river in {cname}", "geography", build_balanced_tiers(items)):
            added += 1

    mtn_rows = datasets.get("mountains_world", [])
    mtn_items = rows_to_scored_items(mtn_rows, alias_map)
    if reg.add("geo-mountain", "Name a famous mountain or peak", "geography", build_balanced_tiers(mtn_items, MAX_SEED_ANSWERS)):
        added += 1

    # Upgrade core seed prompts with deep master_v2 pools (+ aliases)
    for key, _where_b, _min_sl, _lim, pid in SEED_DEEPEN_QUERIES:
        rows = datasets.get(key, [])
        reg.upgrade(pid, rows_to_scored_items(rows, alias_map), MAX_SEED_ANSWERS)

    # 3. Films by decade, year, genre, genre x decade, country, letter
    all_films: list[dict[str, str]] = []
    decade_film_norms: dict[str, dict[str, tuple[str, float, list[str]]]] = {}

    for dlabel, _y0, _y1, _min_sl in FILM_DECADES:
        rows = datasets.get(f"films_{dlabel}", [])
        all_films.extend(rows)
        dec_items = rows_to_scored_items(rows, alias_map)
        dmap: dict[str, tuple[str, float, list[str]]] = {}
        for item in dec_items:
            dmap[normalize_answer(item[0])] = item
        decade_film_norms[dlabel] = dmap
        if reg.add(f"mov-decade-{dlabel}", f"Name a movie from the {dlabel}", "movies", build_balanced_tiers(dec_items, MAX_SEED_ANSWERS)):
            added += 1
        add_group_slices(rows, "year", "mov-year", "Name a movie released in {G}", "movies", min_group=35)
        add_letter_slices(rows, f"mov-{dlabel}", f"Name a {dlabel} movie starting with the letter {{L}}", "movies")

    add_letter_slices(all_films, "mov-all", "Name a movie starting with the letter {L}", "movies")
    one_word_films = [
        r for r in all_films
        if (c := clean_label(r["itemLabel"])) and " " not in c[0] and "-" not in c[0]
    ]
    reg.upgrade("mov-one-word", rows_to_scored_items(one_word_films, alias_map), MAX_SEED_ANSWERS)
    add_letter_slices(one_word_films, "mov-oneword", "Name a one-word movie starting with the letter {L}", "movies")

    genre_film_norms: dict[str, tuple[str, dict[str, tuple[str, float, list[str]]]]] = {}
    for gid, _qid, gname in FILM_GENRES:
        rows = datasets.get(f"film_genre_{gid}", [])
        items = rows_to_scored_items(rows, alias_map)
        gmap: dict[str, tuple[str, float, list[str]]] = {}
        for item in items:
            gmap[normalize_answer(item[0])] = item
        genre_film_norms[gid] = (gname, gmap)
        if reg.add(f"mov-genre-{gid}", f"Name a {gname} movie", "movies", build_balanced_tiers(items, MAX_SEED_ANSWERS)):
            added += 1
        add_letter_slices(rows, f"mov-genre-{gid}", f"Name a {gname} movie starting with the letter {{L}}", "movies")

    if "1990s" in decade_film_norms and "comedy" in genre_film_norms:
        d90 = decade_film_norms["1990s"]
        gcom = genre_film_norms["comedy"][1]
        inter90 = [d90[k] for k in d90 if k in gcom]
        reg.upgrade("mov-90s-comedy", inter90, MAX_SEED_ANSWERS)

    for dlabel in ["1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]:
        dmap = decade_film_norms.get(dlabel, {})
        for gid, (gname, gmap) in genre_film_norms.items():
            if dlabel == "1990s" and gid == "comedy":
                continue
            inter = [dmap[k] for k in dmap if k in gmap]
            if len(inter) >= MIN_ANSWERS:
                if reg.add(
                    f"mov-gd-{dlabel}-{gid}",
                    f"Name a {dlabel} {gname} movie",
                    "movies",
                    build_balanced_tiers(inter),
                ):
                    added += 1

    for cid, _qid, adj in FILM_COUNTRIES:
        rows = datasets.get(f"film_country_{cid}", [])
        items = rows_to_scored_items(rows, alias_map)
        if reg.add(f"mov-country-{cid}", f"Name a {adj} movie", "movies", build_balanced_tiers(items, MAX_SEED_ANSWERS)):
            added += 1
        add_letter_slices(rows, f"mov-country-{cid}", f"Name a {adj} movie starting with the letter {{L}}", "movies")

    # 4. TV Series, Anime, Manga, Songs, Video Games + subgenres
    tv_rows = datasets.get("tv_series_v2", [])
    if reg.add("gen-tv-show", "Name a TV show or series", "general", build_balanced_tiers(rows_to_scored_items(tv_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(tv_rows, "gen-tv", "Name a TV show starting with the letter {L}", "general")

    for code, _qid, adj in TV_COUNTRIES:
        rows = datasets.get(f"tv_{code}", [])
        if reg.add(f"gen-tv-{code}", f"Name a {adj} TV show", "general", build_balanced_tiers(rows_to_scored_items(rows, alias_map), MAX_SEED_ANSWERS)):
            added += 1

    anime_rows = datasets.get("anime_series", [])
    if reg.add("gen-anime", "Name an anime series", "general", build_balanced_tiers(rows_to_scored_items(anime_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(anime_rows, "gen-anime", "Name an anime series starting with the letter {L}", "general")

    manga_rows = datasets.get("manga_series", [])
    if reg.add("gen-manga", "Name a manga series", "general", build_balanced_tiers(rows_to_scored_items(manga_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(manga_rows, "gen-manga", "Name a manga series starting with the letter {L}", "general")

    song_rows = datasets.get("hit_songs", [])
    if reg.add("gen-song", "Name a famous song or single", "general", build_balanced_tiers(rows_to_scored_items(song_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(song_rows, "gen-song", "Name a famous song starting with the letter {L}", "general")

    vg_rows = datasets.get("video_games", [])
    if reg.add("gen-video-game", "Name a video game", "general", build_balanced_tiers(rows_to_scored_items(vg_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(vg_rows, "gen-vg", "Name a video game starting with the letter {L}", "general")

    for gid, gname in [
        ("rpg", "role-playing (RPG)"),
        ("fps", "first-person shooter"),
        ("platformer", "platformer"),
        ("strategy", "strategy"),
        ("racing", "racing"),
        ("fighting", "fighting"),
        ("horror", "survival horror"),
    ]:
        rows = datasets.get(f"vg_genre_{gid}", [])
        if reg.add(f"gen-vg-{gid}", f"Name a {gname} video game", "general", build_balanced_tiers(rows_to_scored_items(rows, alias_map), MAX_SEED_ANSWERS)):
            added += 1

    # 5. Master lists
    for key, _where_b, _min_sl, _lim, pid, ptext, cat, _fb_sl in MASTER_LISTS:
        rows = datasets.get(key, [])
        items = rows_to_scored_items(rows, alias_map)
        if reg.add(pid, ptext, cat, build_balanced_tiers(items, MAX_SEED_ANSWERS)):
            added += 1
        add_letter_slices(rows, pid, f"{ptext} starting with the letter {{L}}", cat)

    # 6. Footballers & animal species
    fb_rows = datasets.get("footballers_v2", [])
    if reg.add("spt-footballer", "Name a professional footballer (soccer player)", "sports", build_balanced_tiers(rows_to_scored_items(fb_rows, alias_map), MAX_SEED_ANSWERS)):
        added += 1
    add_letter_slices(fb_rows, "spt-footballer", "Name a footballer starting with the letter {L}", "sports")

    for key, pid, ptext, cat in [
        ("mammals_en", "gen-mammal", "Name a mammal species", "general"),
        ("birds_en", "gen-bird", "Name a bird species", "general"),
        ("reptiles_en", "gen-reptile", "Name a reptile species", "general"),
        ("fishes_en", "gen-fish", "Name a fish species", "general"),
    ]:
        rows = datasets.get(key, [])
        if reg.add(pid, ptext, cat, build_balanced_tiers(rows_to_scored_items(rows, alias_map), MAX_SEED_ANSWERS)):
            added += 1
        add_letter_slices(rows, pid, f"{ptext} starting with the letter {{L}}", cat)

    # 7. People & places by country
    for key, _qid, _prop, _grp_prop, _min_sl, id_pref, fmt, cat in PEOPLE_COUNTRY_QUERIES:
        rows = datasets.get(key, [])
        add_group_slices(rows, "grpLabel", id_pref, fmt, cat)
        if key == "authors_country":
            author_items = rows_to_scored_items(rows, alias_map)
            if reg.add("gen-author", "Name an author or writer", "general", build_balanced_tiers(author_items, MAX_SEED_ANSWERS)):
                added += 1
            add_letter_slices(rows, "gen-author", "Name an author or writer starting with the letter {L}", "general")

    return added


def enrich_remaining_prompts_with_aliases(
    reg: PromptRegistry,
    datasets: dict[str, list[dict[str, str]]],
    alias_map: dict[str, list[str]],
) -> int:
    """Attach clean Wikidata aliases by normalized canonical label on non-words prompts without collisions."""
    label_best: dict[str, tuple[float, list[str]]] = {}
    for rows in datasets.values():
        for r in rows:
            qid = r.get("qid")
            if not qid or qid not in alias_map or not alias_map[qid]:
                continue
            cleaned = clean_label(r["itemLabel"])
            if not cleaned:
                continue
            canon, base_als = cleaned
            cnorm = normalize_answer(canon)
            if not cnorm:
                continue
            sl = float(r.get("sitelinks", 1) or 1)
            prev = label_best.get(cnorm)
            als = clean_wikidata_aliases(canon, [*base_als, *alias_map[qid]])
            if not als:
                continue
            if prev is None or sl > prev[0]:
                label_best[cnorm] = (sl, als)

    attached_count = 0
    for prompt in reg.prompts:
        if prompt["category"] == "words":
            continue
        tiers_map = prompt["tiers"]
        seen_norms: dict[str, str] = {}
        for t in TIERS:
            for item in tiers_map[t]:
                forms = [item] if isinstance(item, str) else item
                for form in forms:
                    fn = normalize_answer(form)
                    if fn:
                        for v in plural_variants(fn):
                            seen_norms.setdefault(v, t)

        for t in TIERS:
            updated_list: list[Any] = []
            for item in tiers_map[t]:
                if isinstance(item, str):
                    canon, existing_als = item, []
                else:
                    canon, existing_als = item[0], list(item[1:])
                cnorm = normalize_answer(canon)
                cand_info = label_best.get(cnorm)
                if not cand_info:
                    updated_list.append(item)
                    continue
                extra_als = clean_wikidata_aliases(canon, [*existing_als, *cand_info[1]])
                existing_set = {normalize_answer(a) for a in existing_als}
                final_als = list(existing_als)
                added_here = False
                for al in extra_als:
                    if len(final_als) >= MAX_ALIASES_PER_ENTRY:
                        break
                    anorm = normalize_answer(al)
                    if not anorm or anorm in existing_set:
                        continue
                    avars = plural_variants(anorm)
                    if any(v in seen_norms for v in avars):
                        continue
                    for v in avars:
                        seen_norms[v] = t
                    existing_set.add(anorm)
                    final_als.append(al)
                    added_here = True
                    attached_count += 1
                if final_als and added_here:
                    updated_list.append([canon, *final_als])
                elif existing_als:
                    updated_list.append(item)
                else:
                    updated_list.append(canon)
            tiers_map[t] = updated_list

    return attached_count


def load_word_frequencies() -> dict[str, int]:
    freqs: dict[str, int] = {}
    if not WORD_FREQ_PATH.exists():
        return freqs
    with WORD_FREQ_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 2 and parts[0].isalpha():
                freqs[parts[0].lower()] = int(parts[1])
    return freqs


def load_english_dictionary() -> list[tuple[str, float]]:
    words: set[str] = set()
    for dict_path in [
        Path("/usr/share/dict/american-english"),
        Path("/usr/share/dict/british-english"),
    ]:
        if not dict_path.exists():
            continue
        with dict_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                w = line.strip()
                if w and "'" not in w and w.isalpha() and w.islower() and len(w) >= 3:
                    words.add(w)

    freqs = load_word_frequencies()
    scored: list[tuple[str, float]] = []
    for w in words:
        f = freqs.get(w, 0)
        sc = math.log10(f + 1) if f > 0 else max(0.05, 0.9 / max(1, len(w)))
        scored.append((w, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def has_double_pair(word: str) -> bool:
    return any(word[i] == word[i + 1] for i in range(len(word) - 1))


def generate_wordcraft_prompts(reg: PromptRegistry, dict_scored: list[tuple[str, float]]) -> int:
    added = 0

    def emit(pid: str, text: str, words: list[tuple[str, float]]) -> None:
        nonlocal added
        if len(words) < MIN_ANSWERS + 10:
            return
        items = [(w.capitalize(), sc, []) for w, sc in words]
        if reg.add(pid, text, "words", build_balanced_tiers(items, MAX_FACET_ANSWERS)):
            added += 1

    by_len_start: dict[tuple[int, str], list[tuple[str, float]]] = defaultdict(list)
    by_len_end: dict[tuple[int, str], list[tuple[str, float]]] = defaultdict(list)
    by_start_end: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    by_double_char: dict[str, list[tuple[str, float]]] = defaultdict(list)
    by_len_double: dict[int, list[tuple[str, float]]] = defaultdict(list)
    by_start_double: dict[str, list[tuple[str, float]]] = defaultdict(list)
    by_len_rare_ltr: dict[tuple[int, str], list[tuple[str, float]]] = defaultdict(list)
    by_same_start_end: dict[str, list[tuple[str, float]]] = defaultdict(list)

    rare_letters = set("jkqvwxyz")
    for w, sc in dict_scored:
        L = len(w)
        s0, s_end = w[0], w[-1]
        if 3 <= L <= 12:
            by_len_start[(L, s0)].append((w, sc))
        if 4 <= L <= 10:
            by_len_end[(L, s_end)].append((w, sc))
        if L >= 4:
            by_start_end[(s0, s_end)].append((w, sc))
        if L >= 4 and s0 == s_end:
            by_same_start_end[s0].append((w, sc))
        if has_double_pair(w):
            if 5 <= L <= 10:
                by_len_double[L].append((w, sc))
            by_start_double[s0].append((w, sc))
            for ch in set(w):
                if ch * 2 in w:
                    by_double_char[ch].append((w, sc))
        if 5 <= L <= 9:
            for rl in rare_letters:
                if rl in w:
                    by_len_rare_ltr[(L, rl)].append((w, sc))

    for (L, ltr), items in sorted(by_len_start.items()):
        emit(f"wrd-len{L}-{ltr}", f"Name a {L}-letter English word starting with {ltr.upper()}", items)

    for (L, ltr), items in sorted(by_len_end.items()):
        if len(items) >= 40:
            emit(f"wrd-len{L}-end-{ltr}", f"Name a {L}-letter English word ending in {ltr.upper()}", items)

    for (s0, s_end), items in sorted(by_start_end.items()):
        if len(items) >= 34:
            emit(f"wrd-se-{s0}-{s_end}", f"Name an English word starting with {s0.upper()} and ending in {s_end.upper()}", items)

    for ch, items in sorted(by_double_char.items()):
        emit(f"wrd-dbl-{ch}", f"Name an English word containing a double '{ch.upper()}'", items)

    for L, items in sorted(by_len_double.items()):
        emit(f"wrd-dbl-len{L}", f"Name a {L}-letter word containing a double letter", items)

    for ltr, items in sorted(by_start_double.items()):
        emit(f"wrd-dbl-start-{ltr}", f"Name a word starting with {ltr.upper()} that contains a double letter", items)

    for (L, rl), items in sorted(by_len_rare_ltr.items()):
        if len(items) >= 34:
            emit(f"wrd-has-{rl}-len{L}", f"Name a {L}-letter word containing the letter {rl.upper()}", items)

    for ch, items in sorted(by_same_start_end.items()):
        emit(f"wrd-same-se-{ch}", f"Name a word that starts and ends with the letter {ch.upper()}", items)

    suffixes = [
        "tion", "sion", "ment", "ness", "able", "ible", "less", "ful", "ship",
        "hood", "ism", "ist", "ity", "ous", "ive", "ary", "ory", "ize", "ify",
        "ward", "wise", "like", "gram", "graph", "scope", "phone", "phile",
        "cracy", "mania", "meter", "sphere", "dom", "age", "ure", "ance", "ence",
        "ling", "ette", "ster", "eer", "oid", "ical", "ious", "eous", "esque",
        "proof", "bound", "work", "land", "line", "side", "time", "way", "wood",
        "fish", "bird", "stone", "water", "light", "house", "head", "hand",
        "book", "back", "ball", "craft", "field", "form", "mark", "master",
        "ware", "wright", "ly", "er", "or", "al", "ic", "en", "ed", "ing",
        "ian", "ate", "ant", "ent", "logy", "nomy", "pathy", "phobia",
        "metry", "genic", "vore", "cide", "grade", "fold", "some", "most",
    ]
    for suf in suffixes:
        items = [(w, sc) for w, sc in dict_scored if w.endswith(suf) and len(w) > len(suf) + 1]
        emit(f"wrd-suf-{suf}", f'Name an English word ending in "-{suf}"', items)

    prefixes = [
        "un", "re", "pre", "sub", "super", "inter", "trans", "over", "under",
        "out", "mis", "dis", "anti", "auto", "bio", "geo", "hydro", "micro",
        "macro", "mono", "multi", "neo", "omni", "para", "poly", "post", "proto",
        "pseudo", "semi", "tele", "thermo", "tri", "ultra", "counter", "extra",
        "hyper", "infra", "intra", "meta", "mid", "non", "photo", "quad", "retro",
        "self", "fore", "back", "down", "ever", "hand", "head", "high", "home",
        "long", "near", "open", "play", "rain", "sand", "snow", "star", "sun",
        "wind", "wood", "black", "blue", "green", "white", "gold", "grand",
        "hard", "soft", "short", "sweet", "cross", "double", "half", "full",
    ]
    for pre in prefixes:
        items = [(w, sc) for w, sc in dict_scored if w.startswith(pre) and len(w) > len(pre) + 2]
        emit(f"wrd-pre-{pre}", f'Name an English word starting with "{pre}-"', items)

    substrings = [
        "qu", "ph", "ch", "sh", "th", "gh", "kn", "wr", "ck", "ng",
        "oo", "ea", "ou", "ai", "ie", "ei", "cat", "dog", "sun", "sea",
        "ice", "red", "art", "car", "bar", "ear", "arm", "ant", "owl", "rat",
        "bat", "man", "pan", "tin", "pin", "hat", "age", "air", "all", "one",
        "ten", "day", "way", "win", "run", "fun", "top", "pop", "box", "fox",
        "key", "law", "map", "net", "oil", "pen", "pie", "row", "sky", "war",
        "ring", "king", "fire", "tree", "moon", "name", "part", "port", "rock",
        "room", "rose", "ship", "song", "town", "turn", "view", "wall", "wing",
        "word", "year",
    ]
    for sub in substrings:
        items = [(w, sc) for w, sc in dict_scored if sub in w and len(w) >= max(4, len(sub) + 1)]
        emit(f"wrd-sub-{sub}", f'Name an English word containing "{sub.upper()}"', items)

    vowels = set("aeiou")
    left_hand = set("qwertasdfgzxcvb")
    right_hand = set("yuiophjklnm")
    top_row = set("qwertyuiop")

    emit("wrd-3-consec-vowels", "Name an English word with 3 consecutive vowels (e.g. beauty)",
         [(w, sc) for w, sc in dict_scored if re.search(r"[aeiou]{3}", w)])
    emit("wrd-4-consec-cons", "Name an English word with 4 consecutive consonants",
         [(w, sc) for w, sc in dict_scored if re.search(r"[^aeiouy]{4}", w)])
    emit("wrd-no-e-8plus", "Name an 8+ letter English word that does not contain the letter E",
         [(w, sc) for w, sc in dict_scored if len(w) >= 8 and "e" not in w])
    emit("wrd-no-ae-7plus", "Name a 7+ letter English word with neither A nor E",
         [(w, sc) for w, sc in dict_scored if len(w) >= 7 and "a" not in w and "e" not in w])
    for v in "aeiou":
        emit(f"wrd-only-vowel-{v}",
             f"Name a 5+ letter word whose only vowel is {v.upper()} (no other A/E/I/O/U)",
             [(w, sc) for w, sc in dict_scored if len(w) >= 5 and (set(w) & vowels) == {v}])
    emit("wrd-all-5-vowels", "Name a word containing all 5 vowels (A, E, I, O, U)",
         [(w, sc) for w, sc in dict_scored if vowels.issubset(set(w))])
    emit("wrd-left-hand", "Name a 5+ letter word typed using only the left hand on a QWERTY keyboard",
         [(w, sc) for w, sc in dict_scored if len(w) >= 5 and set(w).issubset(left_hand)])
    emit("wrd-right-hand", "Name a 4+ letter word typed using only the right hand on a QWERTY keyboard",
         [(w, sc) for w, sc in dict_scored if len(w) >= 4 and set(w).issubset(right_hand)])
    emit("wrd-top-row", "Name a 5+ letter word typed using only the top QWERTY letter row",
         [(w, sc) for w, sc in dict_scored if len(w) >= 5 and set(w).issubset(top_row)])
    emit("wrd-alpha-order", "Name a 4+ letter word with all letters in alphabetical order (like 'almost')",
         [(w, sc) for w, sc in dict_scored if len(w) >= 4 and list(w) == sorted(w)])
    emit("wrd-isogram-8", "Name an 8+ letter isogram (word with no repeated letters)",
         [(w, sc) for w, sc in dict_scored if len(w) >= 8 and len(set(w)) == len(w)])
    emit("wrd-isogram-9", "Name a 9+ letter isogram (word with no repeated letters)",
         [(w, sc) for w, sc in dict_scored if len(w) >= 9 and len(set(w)) == len(w)])
    emit("wrd-isogram-10", "Name a 10+ letter isogram (word with no repeated letters)",
         [(w, sc) for w, sc in dict_scored if len(w) >= 10 and len(set(w)) == len(w)])

    for L in (5, 6, 7, 8):
        for excl in ("e", "a", "i", "o", "s", "t", "r"):
            emit(f"wrd-len{L}-no-{excl}",
                 f"Name a {L}-letter English word with no letter {excl.upper()}",
                 [(w, sc) for w, sc in dict_scored if len(w) == L and excl not in w])

    for L in (5, 6, 7, 8, 9, 10):
        for suf in ("ing", "ed", "er", "ly", "es", "al", "ic", "en", "tion", "ment", "ness", "able"):
            emit(f"wrd-len{L}-suf-{suf}",
                 f'Name a {L}-letter English word ending in "-{suf}"',
                 [(w, sc) for w, sc in dict_scored if len(w) == L and w.endswith(suf)])

    for L in (6, 7, 8, 9):
        for pre in ("un", "re", "pre", "dis", "out", "over", "sub", "in", "co", "de"):
            emit(f"wrd-len{L}-pre-{pre}",
                 f'Name a {L}-letter English word starting with "{pre}-"',
                 [(w, sc) for w, sc in dict_scored if len(w) == L and w.startswith(pre)])

    for L in (5, 6, 7, 8, 9):
        for sub in ("ch", "sh", "th", "qu", "oo", "ea", "ou", "ai", "st", "tr", "pr", "sp"):
            emit(f"wrd-len{L}-sub-{sub}",
                 f'Name a {L}-letter English word containing "{sub.upper()}"',
                 [(w, sc) for w, sc in dict_scored if len(w) == L and sub in w])

    for L in (5, 6, 7, 8, 9, 10):
        for vcount in (1, 2, 3, 4):
            emit(f"wrd-len{L}-v{vcount}",
                 f"Name a {L}-letter English word with exactly {vcount} {'vowel' if vcount == 1 else 'vowels'} (A/E/I/O/U)",
                 [(w, sc) for w, sc in dict_scored if len(w) == L and sum(1 for c in w if c in vowels) == vcount])

    return added


def chunk_index_for_id(pid: str) -> int:
    digest = hashlib.sha256(pid.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % NUM_CHUNKS


def main() -> None:
    reg = PromptRegistry()

    print("1. Loading 159 existing curated & enriched prompts...")
    load_seed_and_existing(reg)
    print(f"   Loaded {len(reg.prompts)} prompts.")

    print("2. Fetching master_v2 Wikidata datasets (fixed QIDs, broadened P31s, raised limits)...")
    datasets = fetch_all_master_v2_queries()
    all_qids: set[str] = {
        r["qid"] for rows in datasets.values() for r in rows if r.get("qid")
    }
    print(f"   Collected {len(datasets)} datasets covering {len(all_qids):,} unique Wikidata QIDs.")

    print("3. Fetching batched English skos:altLabel aliases from Wikidata...")
    alias_map = fetch_wikidata_aliases(all_qids)

    print("4. Deepening islands & archipelagos (Bonaire, Aruba, Curacao, territories + aliases)...")
    deepen_islands_and_archipelagos(reg, datasets, alias_map)
    print(f"   geo-island: {reg.by_id['geo-island']['answerCount']}, geo-archipelago: {reg.by_id['geo-archipelago']['answerCount']}")

    print("5. Assembling master_v2 Wikidata prompts & upgrades...")
    n_wd = assemble_master_prompts(reg, datasets, alias_map)
    print(f"   Added {n_wd} Wikidata faceted prompts (total: {len(reg.prompts)}).")

    print("6. Enriching remaining non-words seed prompts with Wikidata aliases...")
    n_extra_als = enrich_remaining_prompts_with_aliases(reg, datasets, alias_map)
    print(f"   Attached {n_extra_als:,} extra aliases across remaining seed prompts.")

    print("7. Slicing large core prompts by starting letter (after deepening + aliases)...")
    n_sliced = slice_existing_prompts(reg)
    print(f"   Added {n_sliced} letter-slice prompts (total: {len(reg.prompts)}).")

    print("8. Generating dictionary wordcraft prompts...")
    dict_scored = load_english_dictionary()
    n_words = generate_wordcraft_prompts(reg, dict_scored)
    print(f"   Added {n_words} wordcraft prompts (total: {len(reg.prompts)}).")

    if OUT_CHUNKS_DIR.exists():
        shutil.rmtree(OUT_CHUNKS_DIR)
    OUT_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    if OLD_PROMPTS_DIR.exists():
        shutil.rmtree(OLD_PROMPTS_DIR)

    chunks: list[dict[str, Any]] = [{} for _ in range(NUM_CHUNKS)]
    manifest_entries: list[dict[str, Any]] = []
    total_answers = 0
    total_aliases = 0

    for p in reg.prompts:
        cid = chunk_index_for_id(p["id"])
        chunks[cid][p["id"]] = {"tiers": p["tiers"]}
        manifest_entries.append(
            {
                "id": p["id"],
                "text": p["text"],
                "category": p["category"],
                "answerCount": p["answerCount"],
                "chunk": cid,
            }
        )
        total_answers += p["answerCount"]
        for t in TIERS:
            for item in p["tiers"][t]:
                if isinstance(item, list):
                    total_aliases += len(item) - 1

    max_chunk_bytes = 0
    for cid, payload in enumerate(chunks):
        chunk_path = OUT_CHUNKS_DIR / f"chunk-{cid:03d}.json"
        raw_text = json.dumps(payload, separators=(",", ":"))
        chunk_path.write_text(raw_text, encoding="utf-8")
        max_chunk_bytes = max(max_chunk_bytes, len(raw_text.encode("utf-8")))

    packs_meta = [
        ("words", "WORDS & LANGUAGE", "English quirks, loanwords, and lettercraft", "chapters", "#38bdf8",
         [("Chapter 1: Letter Patterns", "Doubles, palindromes, silent letters & rare starters"),
          ("Chapter 2: Borrowed Tongues", "Loanwords, sheet music & blended portmanteaus"),
          ("Chapter 3: Quirky English", "Collective nouns, sound words, verbs & -ologies"),
          ("Chapter 4: Rhetoric & Ink", "Punctuation, figures of speech, homophones & relics"),
          ("Chapter 5: Lexicon Deep Dive", "Giant words, vowelless gems, NATO & crimsons")]),
        ("movies", "AT THE MOVIES", "Oscars, animation, cults, directors & scores", "pictures", "#f05a84",
         [("Reel 1: Classics & Oscars", "Best Picture, Pixar, Ghibli, Hitchcock & solo titles"),
          ("Reel 2: Genre Vault", "Sci-fi, horror, Disney, 90s comedy & musicals"),
          ("Reel 3: Worlds & Tropes", "Monsters, fictional planets, spies, heists & Westerns"),
          ("Reel 4: Auteurs & Themes", "Directors, composers, time travel, space & sports"),
          ("Reel 5: Cinema Lore", "007, Tarantino, holiday films, silents & Pixar pals")]),
        ("sports", "SPORTS", "Olympians, pro leagues, tactics & arenas", "games", "#34d399",
         [("Match 1: Global Stage", "Olympics, World Cup, Grand Slams, F1 & golf majors"),
          ("Match 2: Pro Franchises", "NBA, NFL, MLB, NHL & Premier League clubs"),
          ("Match 3: Rules & Craft", "Chess, weight classes, track & field, cricket & pitches"),
          ("Match 4: Ice, Pool & Peak", "Winter Games, swimming, gymnastics, cycling & action"),
          ("Match 5: Legends & Hardware", "Stadiums, rugby, Olympians, trophies & gear")]),
        ("geography", "GEOGRAPHY", "Capitals, borders, rivers, peaks & islands", "expeditions", "#fbbf24",
         [("Leg 1: Capitals & Cities", "Europe, US states, South America, Australia & Canada"),
          ("Leg 2: Nations & Borders", "Landlocked, Asia, Africa, microstates & M-nations"),
          ("Leg 3: Water & Landforms", "Rivers, mountain ranges, islands, deserts & seas"),
          ("Leg 4: Wonders & Waters", "Landmarks, national parks, straits, lakes & peninsulas"),
          ("Leg 5: Atlas Oddities", "Flag beasts, Mediterranean, non-Euro, archipelagos & falls")]),
    ]

    seeds_raw: list[dict[str, Any]] = json.loads(SEED_PATH.read_text("utf-8"))
    themed_packs = []
    for cat_id, title, subtitle, unit_label, accent, ch_titles in packs_meta:
        cat_ids = [s["id"] for s in seeds_raw if s["category"] == cat_id]
        chapters = [
            {"id": f"ch-{idx + 1}", "title": ctitle, "subtitle": csub, "promptIds": cat_ids[idx * 5 : idx * 5 + 5]}
            for idx, (ctitle, csub) in enumerate(ch_titles)
        ]
        themed_packs.append(
            {"id": cat_id, "title": title, "subtitle": subtitle, "unitLabel": unit_label, "accentColor": accent, "chapters": chapters}
        )

    year_days = len(manifest_entries) // 7
    manifest_ts = (
        "// Auto-generated by scripts/build_year_database.py\n"
        "import type { PromptMeta, ThemedPack } from '../domain/types';\n\n"
        f"export const TOTAL_ANSWER_COUNT = {total_answers};\n\n"
        f"export const YEAR_COVERAGE_DAYS = {year_days};\n\n"
        f"export const PROMPT_MANIFEST: PromptMeta[] = {json.dumps(manifest_entries, separators=(',', ':'))};\n\n"
        f"export const THEMED_PACKS: ThemedPack[] = {json.dumps(themed_packs, indent=2)};\n"
    )
    OUT_MANIFEST_PATH.write_text(manifest_ts, encoding="utf-8")

    pop_prefixes = (
        "mov-", "gen-tv", "gen-anime", "gen-manga", "gen-song", "gen-vg", "gen-video-game",
        "gen-band", "gen-singer", "gen-album", "gen-superhero", "gen-console", "gen-music-genre",
        "gen-dog-cartoon", "gen-book", "gen-author", "gen-board-game", "gen-card-game", "gen-comic-char",
    )
    pop_count = sum(1 for m in manifest_entries if m["id"].startswith(pop_prefixes))
    cat_counts = Counter(m["category"] for m in manifest_entries)
    print("\n=== DATABASE COMPLETE ===")
    print(f"Total prompts: {len(manifest_entries):,} ({year_days} non-repeating daily dives!)")
    print(f"By category: {dict(cat_counts)}")
    print(f"Pop-culture share: {pop_count:,} / {len(manifest_entries):,} ({pop_count / len(manifest_entries) * 100:.1f}%)")
    print(f"Total answers: {total_answers:,} (+ {total_aliases:,} aliases)")
    print(f"Max chunk size: {max_chunk_bytes / 1024:.1f} KB across {NUM_CHUNKS} chunks")
    for check_pid in [
        "gen-nobel", "gen-compound", "gen-grape", "gen-vg-strategy", "gen-vg-horror",
        "gen-fish", "mov-decade-1950s", "geo-island", "geo-city-am-brazil", "geo-city-am-usa",
    ]:
        p = reg.by_id.get(check_pid)
        print(f"  [Check] {check_pid}: {p['answerCount'] if p else 'MISSING'}")


if __name__ == "__main__":
    main()
