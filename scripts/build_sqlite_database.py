#!/usr/bin/env python3
"""
Build Krillion v1.3.0 Static SQLite-over-HTTP database + manifest:
  1. Loads the 159 curated seed prompts (marking 7 letter-constrained word prompts as packOnly)
  2. Downloads & parses bulk open dumps:
     - GeoNames cities500.zip + countryInfo.txt + admin1CodesASCII.txt (~215k world cities)
     - IMDb title.basics.tsv.gz + title.ratings.tsv.gz (~250k+ movies & TV shows)
  3. Runs batched sitelink-banded Wikidata SPARQL queries (scripts/.cache/bands_v3/)
     for 16 huge non-GeoNames/IMDb categories (islands, rivers, lakes, mountains,
     songs, bands, books, video games, albums, actors, singers, footballers, directors,
     composers, scientists, authors) + broad country/era/genre trivia (scripts/.cache/broad_v3/),
     reusing existing scripts/.cache/master_v2/ and scripts/.cache/aliases_en.json
  4. Expands clean human-friendly variants into relational table entity_forms:
     - exact / article-stripped / plural / Roman numeral / abbreviation forms (kind=0)
     - cleaned aliases / category affix-stripped / subtitle splits (kind=1)
     - person surnames on person prompts (kind=2)
  5. Writes compacted SQLite DB (krillion.sqlite3), splits into 10 MiB static HTTP chunks
     under public/data/db/krillion.sqlite3.000..00N + config.json, removes old public/data/chunks/,
     and writes src/data/manifest.ts.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
BULK_CACHE = CACHE_DIR / "bulk"
MASTER_V2_CACHE = CACHE_DIR / "master_v2"
MASTER_V1_CACHE = CACHE_DIR / "master"
BANDS_V3_CACHE = CACHE_DIR / "bands_v3"
BROAD_V3_CACHE = CACHE_DIR / "broad_v3"
ENRICHED_159_DIR = CACHE_DIR / "enriched_159"
ALIASES_CACHE_PATH = CACHE_DIR / "aliases_en.json"
SQLITE_OUT_PATH = CACHE_DIR / "krillion.sqlite3"

OLD_CHUNKS_DIR = ROOT / "public" / "data" / "chunks"
OLD_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
OUT_DB_DIR = ROOT / "public" / "data" / "db"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

CHUNK_BYTES = 10 * 1024 * 1024  # 10 MiB chunks for sql.js-httpvfs
MAX_DB_BYTES = 195 * 1024 * 1024
TIERS = ["plankton", "tooclever", "schooler", "rare", "deepcut", "krillion"]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "KrillionStaticBuilder/1.4 (https://gitlab.com; static-pages-game)"
MIN_ANSWERS = 30
MAX_FACET_ANSWERS = 1500
MAX_GLOBAL_POOL = 20000
MAX_MEGA_POOL = 100000
MAX_ALIASES_PER_ENTRY = 4

PACK_ONLY_IDS = {
    "geo-country-m",
    "wrd-starts-q",
    "wrd-starts-z",
    "wrd-starts-x",
    "wrd-4letter-verb",
    "wrd-double-consonant",
    "wrd-longest-common",
    "wrd-no-vowels",
}

PERSON_SEED_IDS = {
    "mov-director",
    "mov-actor",
    "mov-film-composer",
    "gen-composer",
    "gen-scientist",
    "gen-painter",
    "gen-singer",
    "gen-author",
    "gen-philosopher",
    "gen-architect",
    "gen-inventor",
    "gen-explorer",
    "gen-monarch",
    "gen-nobel",
    "spt-footballer",
    "spt-nba-player",
    "spt-mlb-player",
    "spt-nfl-player",
    "spt-nhl-player",
    "spt-f1-driver",
    "spt-boxer",
    "spt-chess-player",
    "spt-golfer",
    "spt-swimmer",
    "spt-cyclist",
    "spt-cricketer",
    "spt-olympian",
    "spt-grand-slam-tennis",
    "gen-us-president",
    "gen-uk-pm",
    "gen-roman-emperor",
    "gen-pope",
    "gen-pulitzer",
    "gen-astronaut",
    "gen-astronomer",
    "gen-biologist",
    "gen-chemist",
    "gen-physicist",
    "gen-mathematician",
    "gen-economist",
    "gen-rapper",
    "gen-jazz-musician",
    "gen-guitarist",
    "gen-drummer",
    "gen-pianist",
    "gen-nobel-physics",
    "gen-nobel-chemistry",
    "gen-nobel-medicine",
    "gen-nobel-literature",
    "gen-nobel-peace",
    "gen-nobel-economics",
    "spt-tennis-player",
    "spt-wrestler",
    "spt-skier",
    "spt-gymnast",
    "spt-figure-skater",
    "spt-sprinter",
    "spt-marathon-runner",
}

PERSON_PREFIXES = (
    "gen-author-nat-",
    "gen-actor-nat-",
    "mov-director-nat-",
    "gen-singer-nat-",
    "gen-painter-nat-",
    "gen-composer-nat-",
    "gen-scientist-nat-",
    "gen-philosopher-nat-",
    "gen-architect-nat-",
    "gen-nobel-nat-",
    "spt-footballer-nat-",
    "spt-nba-nat-",
    "spt-tennis-nat-",
    "spt-boxer-nat-",
    "spt-cyclist-nat-",
    "spt-swimmer-nat-",
    "spt-cricketer-nat-",
    "spt-f1-nat-",
    "spt-chess-nat-",
    "spt-nhl-nat-",
    "spt-olympian-nat-",
)

ROMAN_TOKENS = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
    "xiv": "14",
    "xv": "15",
    "xvi": "16",
    "xvii": "17",
    "xviii": "18",
    "xix": "19",
    "xx": "20",
}

ABBREV_MAP = {
    "mt": "mount",
    "st": "saint",
    "dr": "doctor",
    "ft": "fort",
    "pt": "point",
}

LEADING_AFFIXES = (
    "university of ",
    "island of ",
    "isle of ",
    "city of ",
    "town of ",
    "port of ",
    "mount ",
    "saint ",
    "lake ",
    "river ",
    "fort ",
    "mt ",
    "st ",
    "ft ",
    "fc ",
    "cf ",
    "ac ",
    "sc ",
)

TRAILING_AFFIXES = (
    " marine national park",
    " international airport",
    " national park",
    " state park",
    " archipelago",
    " university",
    " mountains",
    " waterfall",
    " peninsula",
    " mountain",
    " islands",
    " volcano",
    " glacier",
    " stadium",
    " airport",
    " college",
    " museum",
    " castle",
    " palace",
    " desert",
    " canyon",
    " cavern",
    " strait",
    " bridge",
    " island",
    " cheese",
    " river",
    " atoll",
    " falls",
    " gorge",
    " canal",
    " arena",
    " bread",
    " sauce",
    " pasta",
    " grape",
    " lake",
    " peak",
    " isle",
    " city",
    " town",
    " cape",
    " cave",
    " park",
    " soup",
    " stew",
    " wine",
    " bay",
    " gulf",
    " mount",
    " afc",
    " fc",
    " cf",
    " ac",
    " sc",
)

AFFIX_STOPWORDS = {
    "new", "old", "big", "red", "blue", "white", "black", "green", "gold",
    "east", "west", "north", "south", "upper", "lower", "great", "little",
    "saint", "san", "los", "las", "sea", "port", "fort", "long", "high",
    "grand", "royal", "king", "queen", "clear", "salt", "rock", "pine",
}

SURNAME_STOPWORDS = {
    "the", "king", "queen", "prince", "princess", "duke", "duchess", "lord",
    "lady", "saint", "pope", "elder", "younger", "great", "emperor", "czar",
    "tsar", "khan", "sultan", "ii", "iii", "iv", "vi", "vii", "viii", "ix",
}

NOISY_ALIAS_SUBSTRINGS = (
    "arcade game",
    "video game",
    "nes ",
    "snes ",
    "game boy",
    "pinball",
    "atari ",
    "soundtrack",
    "hamburgh",
    "mozzart",
    "mozhate",
)

BAD_CURATED_ALIASES = {
    "star wars: the arcade game",
    "nes back to the future",
    "1989 back to the future",
    "hamburgh ſauſage",
    "mozhate",
    "apollo mozzart",
}

# Reused curated island list ensuring Bonaire, Aruba, Curacao & Caribbean islands stay prominent
CURATED_ISLANDS: list[tuple[str, float, list[str]]] = [
    ("Bonaire", 55.0, ["Bonaire Island"]),
    ("Aruba", 85.0, []),
    ("Curacao", 78.0, ["Curaçao"]),
    ("Sint Maarten", 55.0, ["Saint Martin"]),
    ("Saba", 26.0, ["Saba Island"]),
    ("Sint Eustatius", 24.0, ["Statia"]),
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
    ("Puerto Rico", 130.0, []),
    ("Hispaniola", 74.0, []),
    ("Cozumel", 48.0, []),
    ("Isle of Wight", 64.0, []),
    ("Anglesey", 46.0, []),
    ("Isle of Mull", 32.0, ["Mull"]),
    ("Gozo", 42.0, []),
    ("Elba", 52.0, []),
    ("Capri", 62.0, []),
    ("Rhodes", 72.0, []),
    ("Corfu", 68.0, []),
    ("Mykonos", 64.0, []),
    ("Menorca", 54.0, []),
    ("Tenerife", 76.0, []),
    ("Gran Canaria", 68.0, []),
    ("Lanzarote", 58.0, []),
    ("Madeira", 78.0, []),
    ("Bahrain", 96.0, []),
    ("Phuket", 74.0, []),
    ("Singapore", 145.0, []),
    ("Sulawesi", 68.0, []),
    ("Lombok", 52.0, []),
    ("Komodo", 46.0, []),
    ("Timor", 58.0, []),
    ("New Guinea", 86.0, []),
    ("Cebu", 62.0, []),
    ("Palawan", 54.0, []),
    ("Taiwan", 140.0, []),
    ("Hainan", 68.0, []),
    ("Jeju", 66.0, ["Jeju Island"]),
    ("Shikoku", 72.0, []),
    ("Kyushu", 78.0, []),
    ("Okinawa", 84.0, []),
    ("Sakhalin", 64.0, []),
    ("Kangaroo Island", 38.0, []),
    ("Fraser Island", 34.0, ["K'gari"]),
    ("North Island", 72.0, []),
    ("South Island", 72.0, []),
    ("Guam", 82.0, []),
    ("Kauai", 56.0, []),
    ("Vancouver Island", 74.0, []),
    ("Newfoundland", 82.0, []),
    ("Prince Edward Island", 72.0, []),
    ("Long Island", 86.0, []),
    ("Manhattan", 110.0, []),
    ("Staten Island", 74.0, []),
    ("Key West", 62.0, []),
    ("Alcatraz", 72.0, ["Alcatraz Island"]),
    ("Tierra del Fuego", 66.0, []),
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


def normalize_roman_numerals(norm: str) -> str:
    parts = norm.split()
    changed = False
    out = []
    for tok in parts:
        rep = ROMAN_TOKENS.get(tok)
        if rep is not None:
            out.append(rep)
            changed = True
        else:
            out.append(tok)
    return " ".join(out) if changed else norm


def expand_abbreviations(norm: str) -> str:
    parts = norm.split()
    changed = False
    out = []
    for tok in parts:
        rep = ABBREV_MAP.get(tok)
        if rep is not None:
            out.append(rep)
            changed = True
        else:
            out.append(tok)
    return " ".join(out) if changed else norm


def strip_category_affixes(norm: str) -> list[str]:
    results: list[str] = []
    candidates = [norm, expand_abbreviations(norm)]
    for cand in candidates:
        stripped = strip_article(cand)
        for prefix in LEADING_AFFIXES:
            if stripped.startswith(prefix):
                core = strip_article(stripped[len(prefix) :].strip())
                if is_clean_core(core):
                    results.append(core)
        for suffix in TRAILING_AFFIXES:
            if stripped.endswith(suffix):
                core = strip_article(stripped[: -len(suffix)].strip())
                if is_clean_core(core):
                    results.append(core)
    return list(dict.fromkeys(results))


def is_clean_core(core: str) -> bool:
    if not core or len(core) < 3:
        return False
    words = core.split()
    if len(words) == 1 and (len(core) < 4 or core in AFFIX_STOPWORDS):
        return False
    if all(w in AFFIX_STOPWORDS for w in words):
        return False
    return True


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
    if any(bad in label for bad in ["\n", "[", "]", "{", "}", "http://", "https://", "ſ"]):
        return None
    lower = label.lower()
    if lower.startswith(("list of ", "category:", "template:", "wikipedia:", "portal:")):
        return None
    if len(label) > 56 or not re.search(r"[a-zA-Z]", label):
        return None
    aliases: list[str] = []
    m = re.match(r"^(.+?)\s*\([^)]{2,30}\)$", label)
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
    clower = canonical.lower()

    cleaned_candidates: list[str] = []
    for raw in raw_aliases:
        al = raw.strip()
        if len(al) < 2 or len(al) > 38:
            continue
        if any(ch in al for ch in (",", "(", ")", "[", "]", "{", "}", '"', "\n", "\r", "ſ")):
            continue
        if "http://" in al or "https://" in al:
            continue
        if not re.search(r"[a-zA-Z]", al):
            continue
        lower = al.lower()
        if lower in BAD_CURATED_ALIASES:
            continue
        if lower.startswith(("list of ", "category:", "template:", "wikipedia:", "portal:", "file:")):
            continue
        if any(bad in lower and bad not in clower for bad in NOISY_ALIAS_SUBSTRINGS):
            continue
        cleaned_candidates.append(al)

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


def extract_person_surnames(canonical: str) -> list[str]:
    norm = normalize_answer(canonical)
    if not norm:
        return []
    tokens = norm.split()
    while tokens and tokens[-1] in {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md"}:
        tokens.pop()
    if len(tokens) < 2:
        return []

    last = tokens[-1]
    out: list[str] = []
    if len(last) >= 4 and last not in SURNAME_STOPWORDS:
        out.append(last)
    if len(tokens) >= 3 and tokens[-2] in {"van", "von", "de", "da", "del", "della", "di", "la", "le", "dos", "das", "mc", "mac", "o"}:
        compound = f"{tokens[-2]} {last}"
        if len(compound) >= 6:
            out.append(compound)
    return list(dict.fromkeys(out))


def extract_subtitle_variants(canonical: str) -> list[str]:
    out: list[str] = []
    parts: list[str] = []
    if ": " in canonical:
        parts = canonical.split(": ", 1)
    elif " - " in canonical:
        parts = canonical.split(" - ", 1)
    if len(parts) != 2:
        return out
    head = normalize_answer(parts[0])
    tail = normalize_answer(parts[1])
    if len(head) >= 4 and head not in {"part", "volume", "vol", "book", "chapter", "episode"}:
        out.extend([head, strip_article(head), normalize_roman_numerals(head)])
    if len(tail) >= 5 and len(tail.split()) >= 2:
        out.extend([tail, strip_article(tail), normalize_roman_numerals(tail)])
    return [x for x in dict.fromkeys(out) if len(x) >= 4]


def prompt_form_level(pid: str, category: str) -> int:
    if category == "words":
        return 0
    if pid in PERSON_SEED_IDS or pid.startswith(PERSON_PREFIXES):
        return 2
    return 1


def post_sparql(query: str, timeout: int = 24) -> dict[str, Any]:
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


def run_sparql_cached(
    cache_dir: Path,
    name: str,
    query: str,
    allow_v1_v2_fallback: bool = True,
) -> list[dict[str, str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{name}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text("utf-8"))
        if len(data) > 0:
            return data

    if allow_v1_v2_fallback:
        for fallback_dir in (MASTER_V2_CACHE, MASTER_V1_CACHE):
            fb = fallback_dir / f"{name}.json"
            if fb.exists():
                data = json.loads(fb.read_text("utf-8"))
                if len(data) > 0:
                    return data

    for attempt, delay in enumerate([0.4, 1.5, 3.2]):
        try:
            time.sleep(delay)
            payload = post_sparql(query, timeout=24)
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
            print(f"  [SPARQL] {name}: {len(rows)} rows")
            return rows
        except urllib.error.HTTPError as exc:
            print(f"  [SPARQL retry {attempt + 1}] {name}: HTTP {exc.code}")
            if exc.code == 429:
                time.sleep(5.0 * (attempt + 1))
        except Exception as exc:
            print(f"  [SPARQL retry {attempt + 1}] {name}: {exc}")
    return []


def run_batched_sparql_bands(
    name: str,
    where_body: str,
    bands: list[tuple[int, int | None]],
    per_band_limit: int = 5500,
    distinct: bool = False,
) -> list[dict[str, str]]:
    """Query non-overlapping sitelink bands to bypass Blazegraph global-sort timeouts."""
    BANDS_V3_CACHE.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, str]] = []
    dist = "DISTINCT " if distinct else ""
    for low, high in bands:
        tag = f"{name}_{low}_{high if high is not None else 'top'}"
        if high is None:
            sl_filter = f"FILTER(?sitelinks >= {low})"
        else:
            sl_filter = f"FILTER(?sitelinks >= {low} && ?sitelinks < {high})"
        q = f"""
SELECT {dist}?item ?itemLabel ?sitelinks WHERE {{
{where_body}
  ?item wikibase:sitelinks ?sitelinks .
  {sl_filter}
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
}} LIMIT {per_band_limit}""".strip()
        band_rows = run_sparql_cached(BANDS_V3_CACHE, tag, q, allow_v1_v2_fallback=False)
        all_rows.extend(band_rows)
    return dedup_rows_by_qid(all_rows)


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
        if float(row.get("sitelinks", 1) or 1) > float(prev.get("sitelinks", 1) or 1):
            prev["sitelinks"] = row.get("sitelinks", prev.get("sitelinks", "1"))
        if keep_min_year and row.get("year") and prev.get("year"):
            if row["year"].isdigit() and prev["year"].isdigit() and int(row["year"]) < int(prev["year"]):
                prev["year"] = row["year"]
    return list(by_qid.values()) + passthrough


def fetch_wikidata_aliases(qids: set[str]) -> dict[str, list[str]]:
    ALIASES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    alias_cache: dict[str, list[str]] = {}
    if ALIASES_CACHE_PATH.exists():
        alias_cache = json.loads(ALIASES_CACHE_PATH.read_text("utf-8"))

    missing = sorted(q for q in qids if q and q not in alias_cache)
    if not missing:
        print(f"  [Aliases] Loaded {len(alias_cache):,} cached QIDs (0 new high-sitelink QIDs).")
        return alias_cache

    batch_size = 400
    total_batches = (len(missing) + batch_size - 1) // batch_size
    print(f"  [Aliases] Fetching English skos:altLabel for {len(missing):,} new QIDs in {total_batches} batches...")

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
                payload = post_sparql(q, timeout=24)
                for b in payload.get("results", {}).get("bindings", []):
                    item_uri = b.get("item", {}).get("value", "")
                    alt_val = b.get("alt", {}).get("value", "").strip()
                    qid = item_uri.rsplit("/", 1)[-1]
                    if qid in fetched and alt_val:
                        fetched[qid].append(alt_val)
                ok = True
                break
            except Exception as exc:
                print(f"  [Aliases batch {b_idx + 1}/{total_batches} retry {attempt + 1}] {exc}")
        if ok:
            for qid, als in fetched.items():
                alias_cache[qid] = list(dict.fromkeys(als))
        if (b_idx + 1) % 15 == 0 or (b_idx + 1) == total_batches:
            ALIASES_CACHE_PATH.write_text(json.dumps(alias_cache, separators=(",", ":")), encoding="utf-8")

    return alias_cache


def download_if_missing(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    print(f"  [Download] {url} -> {dest.name}...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh, length=1024 * 512)
    tmp.replace(dest)
    print(f"  [Download] Saved {dest.name} ({dest.stat().st_size / (1024 * 1024):.1f} MB)")
    return dest


def download_bulk_datasets() -> tuple[Path, Path, Path, Path, Path]:
    c_zip = download_if_missing("https://download.geonames.org/export/dump/cities500.zip", BULK_CACHE / "cities500.zip")
    c_info = download_if_missing("https://download.geonames.org/export/dump/countryInfo.txt", BULK_CACHE / "countryInfo.txt")
    a1 = download_if_missing("https://download.geonames.org/export/dump/admin1CodesASCII.txt", BULK_CACHE / "admin1CodesASCII.txt")
    i_rat = download_if_missing("https://datasets.imdbws.com/title.ratings.tsv.gz", BULK_CACHE / "title.ratings.tsv.gz")
    i_bas = download_if_missing("https://datasets.imdbws.com/title.basics.tsv.gz", BULK_CACHE / "title.basics.tsv.gz")
    return c_zip, c_info, a1, i_rat, i_bas


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
        for al in clean_wikidata_aliases(canon, aliases):
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
    max_total: int = MAX_GLOBAL_POOL,
) -> dict[str, list[Any]]:
    tier_weight = {
        "plankton": 10_000_000.0,
        "tooclever": 1_000_000.0,
        "schooler": 250_000.0,
        "rare": 50_000.0,
        "deepcut": 5_000.0,
        "krillion": 500.0,
    }
    combined: list[tuple[str, float, list[str]]] = []
    for t in TIERS:
        for item in base_tiers[t]:
            if isinstance(item, str):
                combined.append((item, tier_weight[t], []))
            else:
                cleaned = clean_wikidata_aliases(item[0], item[1:])
                combined.append((item[0], tier_weight[t], cleaned))
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
        pack_only: bool = False,
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
            "packOnly": pack_only or (pid in PACK_ONLY_IDS),
        }
        self.prompts.append(obj)
        self.by_id[pid] = obj
        self.seen_texts.add(tkey)
        return True

    def upgrade(
        self,
        pid: str,
        additions: list[tuple[str, float, list[str]]],
        max_total: int = MAX_GLOBAL_POOL,
    ) -> None:
        existing = self.by_id.get(pid)
        if not existing or not additions:
            return
        new_tiers = merge_additional_into_tiers(existing["tiers"], additions, max_total)
        existing["tiers"] = new_tiers
        existing["answerCount"] = sum(len(v) for v in new_tiers.values())


def load_seed_159(reg: PromptRegistry) -> None:
    seeds: list[dict[str, Any]] = json.loads(SEED_PATH.read_text("utf-8"))
    for seed in seeds:
        pid = seed["id"]
        cached_json_path = ENRICHED_159_DIR / f"{pid}.json"
        if cached_json_path.exists():
            raw = json.loads(cached_json_path.read_text("utf-8"))
            tiers_map: dict[str, list[Any]] = {t: [] for t in TIERS}
            for t in TIERS:
                for it in raw["tiers"][t]:
                    if isinstance(it, str):
                        tiers_map[t].append(it)
                    else:
                        cls = clean_wikidata_aliases(it[0], it[1:])
                        tiers_map[t].append([it[0], *cls] if cls else it[0])
        else:
            tiers_map = {t: [] for t in TIERS}
            for ans in seed["answers"]:
                if ans.get("aliases"):
                    tiers_map[ans["tier"]].append([ans["canonical"], *ans["aliases"]])
                else:
                    tiers_map[ans["tier"]].append(ans["canonical"])
        reg.add(pid, seed["text"], seed["category"], tiers_map, pack_only=(pid in PACK_ONLY_IDS))


def process_geonames_bulk(
    reg: PromptRegistry,
    cities_zip: Path,
    country_info_path: Path,
    admin1_path: Path,
) -> int:
    country_names: dict[str, str] = {}
    country_continent: dict[str, str] = {}
    for line in country_info_path.read_text("utf-8", errors="ignore").splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 9:
            iso2 = cols[0].strip()
            country_names[iso2] = cols[4].strip()
            country_continent[iso2] = cols[8].strip()

    admin1_names: dict[str, str] = {}
    for line in admin1_path.read_text("utf-8", errors="ignore").splitlines():
        cols = line.split("\t")
        if len(cols) >= 3:
            admin1_names[cols[0].strip()] = cols[2].strip() or cols[1].strip()

    world_items: list[tuple[str, float, list[str]]] = []
    by_continent: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    by_country: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    by_admin1: dict[tuple[str, str], list[tuple[str, float, list[str]]]] = defaultdict(list)

    print("  [GeoNames] Parsing cities500.zip...")
    with zipfile.ZipFile(cities_zip) as zf:
        with zf.open("cities500.txt") as raw_fh:
            for raw_line in io.TextIOWrapper(raw_fh, encoding="utf-8", errors="ignore"):
                cols = raw_line.rstrip("\n").split("\t")
                if len(cols) < 15:
                    continue
                name = cols[1].strip()
                asciiname = cols[2].strip()
                alt_raw = cols[3].strip()
                cc = cols[8].strip()
                a1 = cols[10].strip()
                try:
                    pop = float(int(cols[14]) + 1)
                except ValueError:
                    pop = 1.0

                if not name or len(name) > 52 or not re.search(r"[a-zA-Z]", name):
                    continue
                als: list[str] = []
                if asciiname and asciiname.lower() != name.lower():
                    als.append(asciiname)
                if alt_raw:
                    for part in alt_raw.split(","):
                        p = part.strip()
                        if 2 <= len(p) <= 34 and re.fullmatch(r"[A-Za-z0-9\s.'\-]+", p):
                            als.append(p)
                            if len(als) >= 6:
                                break
                cleaned_als = clean_wikidata_aliases(name, als, max_aliases=3)
                # Rank weight smoothly compresses giant megacities vs towns
                score = math.log10(pop + 10.0) * 20.0 + (pop / 500_000.0)
                item = (name, score, cleaned_als)
                world_items.append(item)
                if cc in country_continent:
                    by_continent[country_continent[cc]].append(item)
                if cc in country_names:
                    by_country[cc].append(item)
                adm_key = f"{cc}.{a1}"
                if a1 and adm_key in admin1_names:
                    reg_name = admin1_names[adm_key]
                    if reg_name and not reg_name.isdigit() and re.search(r"[a-zA-Z]{2,}", reg_name):
                        by_admin1[(cc, reg_name)].append(item)

    added = 0
    if reg.add("geo-world-city", "Name any city or town in the world", "geography", build_balanced_tiers(world_items, MAX_MEGA_POOL)):
        added += 1

    cont_labels = {
        "EU": ("eu", "European"),
        "AS": ("as", "Asian"),
        "AF": ("af", "African"),
        "NA": ("na", "North American"),
        "SA": ("sa", "South American"),
        "OC": ("oc", "Oceanian"),
    }
    for cont_code, (slug, adj) in cont_labels.items():
        items = by_continent.get(cont_code, [])
        if reg.add(f"geo-city-{slug}", f"Name a {adj} city or town", "geography", build_balanced_tiers(items, MAX_GLOBAL_POOL)):
            added += 1

    # Upgrade SA / AU / CA existing seed city prompts
    reg.upgrade("geo-south-america-city", by_continent.get("SA", []), MAX_GLOBAL_POOL)
    reg.upgrade("geo-australia-city", by_country.get("AU", []), MAX_GLOBAL_POOL)
    reg.upgrade("geo-canada-city", by_country.get("CA", []), MAX_GLOBAL_POOL)

    major_country_caps = {"US": 25000, "GB": 8000, "DE": 8000, "FR": 8000, "IN": 8000, "BR": 8000, "CN": 8000, "MX": 6000, "CA": 6000, "AU": 6000, "IT": 6000, "ES": 6000, "JP": 6000, "RU": 6000}
    am_existing = {"US": "usa", "CA": "canada", "MX": "mexico", "BR": "brazil", "AR": "argentina", "CO": "colombia", "PE": "peru", "CL": "chile"}
    am_labels = {"US": "the United States", "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "AR": "Argentina", "CO": "Colombia", "PE": "Peru", "CL": "Chile"}
    for cc, items in sorted(by_country.items()):
        if len(items) < MIN_ANSWERS:
            continue
        cname = country_names[cc]
        cap = major_country_caps.get(cc, 2000)
        if cc in am_existing:
            pid = f"geo-city-am-{am_existing[cc]}"
            if reg.add(pid, f"Name a city in {am_labels[cc]}", "geography", build_balanced_tiers(items, cap)):
                added += 1
        else:
            cont_slug = cont_labels.get(country_continent.get(cc, ""), ("world", ""))[0]
            cslug = re.sub(r"[^a-z0-9]+", "-", cname.lower()).strip("-")
            if reg.add(f"geo-city-{cont_slug}-{cslug}", f"Name a city in {cname}", "geography", build_balanced_tiers(items, cap)):
                added += 1

    # U.S. states (all 50) + major recognizable states/provinces/regions worldwide
    allowed_region_countries = {
        "US", "CA", "AU", "GB", "DE", "FR", "IT", "ES", "IN", "BR", "MX",
        "JP", "CN", "RU", "AR", "CO", "PL", "NL", "CH", "AT",
        "SE", "NO", "TR", "ZA", "ID", "PH", "TH", "KR", "IE",
    }
    for (cc, rname), items in sorted(by_admin1.items()):
        if cc not in allowed_region_countries or len(items) < MIN_ANSWERS:
            continue
        rslug = re.sub(r"[^a-z0-9]+", "-", rname.lower()).strip("-")
        if cc == "US":
            if reg.add(f"geo-us-city-{rslug}", f"Name a city in {rname}", "geography", build_balanced_tiers(items, 1200)):
                added += 1
        else:
            cname = country_names.get(cc, cc)
            if rname.lower() == cname.lower():
                continue
            if reg.add(
                f"geo-reg-city-{cc.lower()}-{rslug}",
                f"Name a city or town in {rname}, {cname}",
                "geography",
                build_balanced_tiers(items, 800),
            ):
                added += 1

    print(f"  [GeoNames] Added {added} broad city prompts ({len(world_items):,} world cities loaded).")
    return added


def process_imdb_bulk(
    reg: PromptRegistry,
    ratings_gz: Path,
    basics_gz: Path,
) -> int:
    print("  [IMDb] Reading title.ratings.tsv.gz...")
    votes_by_tconst: dict[str, int] = {}
    with gzip.open(ratings_gz, "rt", encoding="utf-8", errors="ignore") as fh:
        next(fh, None)
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 3:
                votes = int(cols[2])
                if votes >= 25:
                    votes_by_tconst[cols[0]] = votes
    print(f"  [IMDb] Indexed {len(votes_by_tconst):,} titles with >= 25 votes.")

    all_movies: list[tuple[str, float, list[str]]] = []
    all_tv: list[tuple[str, float, list[str]]] = []
    one_word_movies: list[tuple[str, float, list[str]]] = []
    movies_by_decade: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    movies_by_year: dict[int, list[tuple[str, float, list[str]]]] = defaultdict(list)
    movies_by_genre: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    movies_by_dg: dict[tuple[str, str], list[tuple[str, float, list[str]]]] = defaultdict(list)
    movies_by_yg: dict[tuple[int, str], list[tuple[str, float, list[str]]]] = defaultdict(list)
    movies_by_gg: dict[tuple[str, str], list[tuple[str, float, list[str]]]] = defaultdict(list)
    tv_by_decade: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    tv_by_year: dict[int, list[tuple[str, float, list[str]]]] = defaultdict(list)
    tv_by_genre: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
    tv_by_dg: dict[tuple[str, str], list[tuple[str, float, list[str]]]] = defaultdict(list)
    tv_by_gg: dict[tuple[str, str], list[tuple[str, float, list[str]]]] = defaultdict(list)

    gg_pairs = [
        ("Action", "Comedy"), ("Action", "Adventure"), ("Action", "Crime"), ("Action", "Sci-Fi"),
        ("Action", "Thriller"), ("Adventure", "Animation"), ("Adventure", "Family"), ("Adventure", "Fantasy"),
        ("Adventure", "Sci-Fi"), ("Animation", "Comedy"), ("Animation", "Family"), ("Biography", "Drama"),
        ("Comedy", "Crime"), ("Comedy", "Drama"), ("Comedy", "Family"), ("Comedy", "Fantasy"),
        ("Comedy", "Horror"), ("Comedy", "Musical"), ("Comedy", "Romance"), ("Comedy", "Sci-Fi"),
        ("Comedy", "Sport"), ("Crime", "Drama"), ("Crime", "Mystery"), ("Crime", "Thriller"),
        ("Drama", "History"), ("Drama", "Music"), ("Drama", "Mystery"), ("Drama", "Romance"),
        ("Drama", "Sport"), ("Drama", "Thriller"), ("Drama", "War"), ("Drama", "Western"),
        ("Fantasy", "Horror"), ("Horror", "Mystery"), ("Horror", "Sci-Fi"), ("Horror", "Thriller"),
        ("Mystery", "Thriller"), ("Romance", "Sci-Fi"),
    ]
    tv_gg_pairs = [
        ("Comedy", "Drama"), ("Crime", "Drama"), ("Crime", "Thriller"), ("Crime", "Mystery"),
        ("Action", "Adventure"), ("Animation", "Comedy"), ("Drama", "Mystery"), ("Drama", "Romance"),
        ("Drama", "Thriller"), ("Drama", "Sci-Fi"), ("Comedy", "Romance"), ("Comedy", "Sci-Fi"),
        ("Adventure", "Comedy"), ("Action", "Comedy"), ("Action", "Drama"), ("Action", "Sci-Fi"),
    ]
    top_yg_genres = {
        "Action", "Adventure", "Animation", "Comedy", "Crime",
        "Documentary", "Drama", "Horror", "Romance", "Sci-Fi", "Thriller",
    }

    print("  [IMDb] Streaming title.basics.tsv.gz...")
    with gzip.open(basics_gz, "rt", encoding="utf-8", errors="ignore") as fh:
        next(fh, None)
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 9:
                continue
            tconst = cols[0]
            votes = votes_by_tconst.get(tconst)
            if votes is None:
                continue
            ttype = cols[1]
            if ttype not in {"movie", "tvSeries", "tvMiniSeries"}:
                continue
            if cols[4] != "0":
                continue

            title = cols[2].strip()
            if not title or len(title) > 54 or not re.search(r"[a-zA-Z]", title):
                continue
            orig = cols[3].strip()
            als: list[str] = []
            if orig and orig != r"\N" and orig.lower() != title.lower() and re.fullmatch(r"[A-Za-z0-9\s.'\-:!?&]+", orig) and len(orig) <= 38:
                als.append(orig)

            year_str = cols[5]
            year = int(year_str) if year_str.isdigit() else 0
            genres_raw = cols[8]
            genres = [g.strip() for g in genres_raw.split(",") if g.strip() and g != r"\N"]
            score = float(votes)
            item = (title, score, als)

            if ttype == "movie":
                all_movies.append(item)
                if " " not in title and "-" not in title and ":" not in title:
                    one_word_movies.append(item)
                decade = f"{(year // 10) * 10}s" if 1920 <= year <= 2029 else ""
                if decade:
                    movies_by_decade[decade].append(item)
                if 1930 <= year <= 2025:
                    movies_by_year[year].append(item)
                for g in genres:
                    movies_by_genre[g].append(item)
                    if decade and year >= 1950:
                        movies_by_dg[(decade, g)].append(item)
                    if 1980 <= year <= 2025 and g in top_yg_genres:
                        movies_by_yg[(year, g)].append(item)
                gset = set(genres)
                for g1, g2 in gg_pairs:
                    if g1 in gset and g2 in gset:
                        movies_by_gg[(g1, g2)].append(item)
            else:
                all_tv.append(item)
                decade = f"{(year // 10) * 10}s" if 1950 <= year <= 2029 else ""
                if decade:
                    tv_by_decade[decade].append(item)
                if 1970 <= year <= 2025:
                    tv_by_year[year].append(item)
                for g in genres:
                    tv_by_genre[g].append(item)
                    if decade and year >= 1970:
                        tv_by_dg[(decade, g)].append(item)
                gset = set(genres)
                for g1, g2 in tv_gg_pairs:
                    if g1 in gset and g2 in gset:
                        tv_by_gg[(g1, g2)].append(item)

    added = 0
    if reg.add("mov-any-movie", "Name any movie", "movies", build_balanced_tiers(all_movies, MAX_MEGA_POOL)):
        added += 1
    if reg.add("gen-tv-show", "Name a TV show or series", "general", build_balanced_tiers(all_tv, 40000)):
        added += 1

    # Upgrade core movie prompts cleanly
    reg.upgrade("mov-one-word", one_word_movies, MAX_GLOBAL_POOL)
    reg.upgrade("mov-scifi-classic", movies_by_genre.get("Sci-Fi", []), MAX_GLOBAL_POOL)
    reg.upgrade("mov-horror", movies_by_genre.get("Horror", []), MAX_GLOBAL_POOL)
    reg.upgrade("mov-western", movies_by_genre.get("Western", []), MAX_GLOBAL_POOL)
    reg.upgrade("mov-musical", movies_by_genre.get("Musical", []), MAX_GLOBAL_POOL)
    reg.upgrade("mov-sports", movies_by_genre.get("Sport", []), MAX_GLOBAL_POOL)
    reg.upgrade("mov-90s-comedy", movies_by_dg.get(("1990s", "Comedy"), []), MAX_GLOBAL_POOL)

    def art(word: str) -> str:
        return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"

    for dlabel, items in sorted(movies_by_decade.items()):
        if reg.add(f"mov-decade-{dlabel}", f"Name a movie from the {dlabel}", "movies", build_balanced_tiers(items, 12000)):
            added += 1
    for y, items in sorted(movies_by_year.items()):
        if reg.add(f"mov-year-{y}", f"Name a movie released in {y}", "movies", build_balanced_tiers(items, 1200)):
            added += 1

    genre_slug_map = {"Sci-Fi": ("scifi", "Sci-Fi"), "Biography": ("biopic", "Biographical"), "Film-Noir": ("film-noir", "Film Noir"), "Sport": ("sports", "Sports")}
    for g, items in sorted(movies_by_genre.items()):
        gslug, gdisp = genre_slug_map.get(g, (g.lower(), g))
        if reg.add(f"mov-genre-{gslug}", f"Name {art(gdisp)} {gdisp} movie", "movies", build_balanced_tiers(items, 12000)):
            added += 1

    for (dlabel, g), items in sorted(movies_by_dg.items()):
        gslug, gdisp = genre_slug_map.get(g, (g.lower(), g))
        if len(items) >= MIN_ANSWERS + 10:
            if reg.add(f"mov-gd-{dlabel}-{gslug}", f"Name a {dlabel} {gdisp} movie", "movies", build_balanced_tiers(items, 1200)):
                added += 1

    for (g1, g2), items in sorted(movies_by_gg.items()):
        if len(items) >= MIN_ANSWERS + 15:
            slug = f"{g1.lower()}-{g2.lower()}"
            disp = "Romantic Comedy" if (g1, g2) == ("Comedy", "Romance") else f"{g1} {g2}"
            if reg.add(f"mov-gg-{slug}", f"Name {art(disp)} {disp} movie", "movies", build_balanced_tiers(items, 1200)):
                added += 1

    for (y, g), items in sorted(movies_by_yg.items()):
        if y >= 1985 and g in top_yg_genres and len(items) >= 45:
            gslug, gdisp = genre_slug_map.get(g, (g.lower(), g))
            if reg.add(f"mov-yg-{y}-{gslug}", f"Name {art(gdisp)} {gdisp} movie released in {y}", "movies", build_balanced_tiers(items, 450)):
                added += 1

    for dlabel, items in sorted(tv_by_decade.items()):
        if reg.add(f"gen-tv-decade-{dlabel}", f"Name a TV show from the {dlabel}", "general", build_balanced_tiers(items, 6000)):
            added += 1
    for y, items in sorted(tv_by_year.items()):
        if len(items) >= 35:
            if reg.add(f"gen-tv-year-{y}", f"Name a TV show that premiered in {y}", "general", build_balanced_tiers(items, 1000)):
                added += 1
    for g, items in sorted(tv_by_genre.items()):
        gslug, gdisp = genre_slug_map.get(g, (g.lower(), g))
        if reg.add(f"gen-tv-genre-{gslug}", f"Name {art(gdisp)} {gdisp} TV show", "general", build_balanced_tiers(items, 5000)):
            added += 1
    for (dlabel, g), items in sorted(tv_by_dg.items()):
        gslug, gdisp = genre_slug_map.get(g, (g.lower(), g))
        if len(items) >= 35:
            if reg.add(f"gen-tv-gd-{dlabel}-{gslug}", f"Name a {dlabel} {gdisp} TV show", "general", build_balanced_tiers(items, 1000)):
                added += 1
    for (g1, g2), items in sorted(tv_by_gg.items()):
        if len(items) >= 40:
            slug = f"{g1.lower()}-{g2.lower()}"
            disp = "Comedy-Drama" if (g1, g2) == ("Comedy", "Drama") else f"{g1} {g2}"
            if reg.add(f"gen-tv-gg-{slug}", f"Name {art(disp)} {disp} TV show", "general", build_balanced_tiers(items, 1200)):
                added += 1

    print(f"  [IMDb] Added {added} broad movie & TV prompts ({len(all_movies):,} movies, {len(all_tv):,} TV series).")
    return added


def rows_to_scored(rows: list[dict[str, str]], alias_map: dict[str, list[str]]) -> list[tuple[str, float, list[str]]]:
    items: list[tuple[str, float, list[str]]] = []
    for r in rows:
        cleaned = clean_label(r["itemLabel"])
        if not cleaned:
            continue
        canon, base_als = cleaned
        sl = float(r.get("sitelinks", 1) or 1)
        qid = r.get("qid", "")
        raw_als = list(base_als)
        if qid and qid in alias_map:
            raw_als.extend(alias_map[qid])
        items.append((canon, sl, clean_wikidata_aliases(canon, raw_als)))
    return items


def run_wikidata_batches_and_broad(reg: PromptRegistry) -> None:
    # 1. Batched sitelink-banded queries for the 16 huge non-GeoNames/non-IMDb categories
    banded_specs: list[tuple[str, str, list[tuple[int, int | None]], bool, str, str, str, bool]] = [
        # (cache_name, where_body, bands, distinct, pid, ptext, cat, upgrade_existing)
        ("band_islands", "  ?item wdt:P31 wd:Q23442 .", [(20, None), (10, 20), (5, 10), (3, 5)], False, "geo-island", "Name an island (not a continent)", "geography", True),
        ("band_rivers", "  ?item wdt:P31 wd:Q4022 .", [(20, None), (10, 20), (5, 10), (3, 5)], False, "geo-river", "Name a famous river", "geography", True),
        ("band_lakes", "  ?item wdt:P31 wd:Q23397 .", [(15, None), (8, 15), (4, 8), (2, 4)], False, "geo-lake", "Name a famous lake", "geography", True),
        ("band_mountains", "  ?item wdt:P31 wd:Q8502 .", [(20, None), (10, 20), (5, 10), (3, 5)], False, "geo-mountain", "Name a famous mountain or peak", "geography", False),
        ("band_songs", "  ?item wdt:P31 wd:Q134556 .", [(25, None), (14, 25), (8, 14)], False, "gen-song", "Name a famous song or single", "general", False),
        ("band_bands", "  ?item wdt:P31 wd:Q215380 .", [(25, None), (14, 25), (8, 14)], False, "gen-band", "Name a musical band or group", "general", False),
        ("band_books", "  ?item wdt:P31 wd:Q7725634 .", [(25, None), (14, 25), (8, 14)], False, "gen-book", "Name a famous book or novel", "general", False),
        ("band_games", "  ?item wdt:P31 wd:Q7889 .", [(25, None), (14, 25), (8, 14)], False, "gen-video-game", "Name a video game", "general", False),
        ("band_albums", "  ?item wdt:P31 wd:Q482994 .", [(20, None), (11, 20), (6, 11)], False, "gen-album", "Name a studio album", "general", False),
        ("band_actors", "  ?item wdt:P106 wd:Q33999 .", [(45, None), (28, 45), (18, 28)], False, "mov-actor", "Name a film or TV actor", "movies", False),
        ("band_singers", "  ?item wdt:P106 wd:Q177220 .", [(40, None), (25, 40), (16, 25)], False, "gen-singer", "Name a singer or vocalist", "general", False),
        ("band_footballers", "  ?item wdt:P106 wd:Q937857 .", [(50, None), (32, 50), (20, 32)], False, "spt-footballer", "Name a professional footballer (soccer player)", "sports", False),
        ("band_directors", "  ?item wdt:P106 wd:Q2526255 .", [(30, None), (16, 30), (9, 16)], False, "mov-director", "Name a famous film director", "movies", True),
        ("band_composers", "  ?item wdt:P106 wd:Q36834 .", [(20, None), (10, 20), (5, 10)], False, "gen-composer", "Name a classical composer", "general", True),
        ("band_scientists", "  ?item wdt:P106 wd:Q901 .", [(25, None), (14, 25), (8, 14)], False, "gen-scientist", "Name a famous scientist", "general", True),
        ("band_authors", "  ?item wdt:P106 wd:Q36180 .", [(40, None), (25, 40), (16, 25)], False, "gen-author", "Name an author or writer", "general", False),
    ]

    banded_data: dict[str, list[dict[str, str]]] = {}
    for bname, where_b, bands, dist, *_rest in banded_specs:
        banded_data[bname] = run_batched_sparql_bands(bname, where_b, bands, per_band_limit=5500, distinct=dist)

    # 2. Load existing master_v2 datasets + new standalone broad trivia + natural country/platform/genre facets
    def q_simple(where_b: str, min_sl: int, lim: int = 3500, distinct: bool = False) -> str:
        dist = "DISTINCT " if distinct else ""
        return f"""
SELECT {dist}?item ?itemLabel ?sitelinks WHERE {{
{where_b}
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
}} LIMIT {lim}""".strip()

    def q_grouped(where_b: str, grp_var: str, min_sl: int, lim: int = 5000) -> str:
        return f"""
SELECT DISTINCT ?item ?itemLabel ?{grp_var}Label ?sitelinks WHERE {{
{where_b}
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  ?{grp_var} rdfs:label ?{grp_var}Label . FILTER(LANG(?{grp_var}Label) = "en")
}} LIMIT {lim}""".strip()

    # Reuse all already-cached master_v2 files
    master_datasets: dict[str, list[dict[str, str]]] = {}
    for p in sorted(MASTER_V2_CACHE.glob("*.json")):
        master_datasets[p.stem] = dedup_rows_by_qid(json.loads(p.read_text("utf-8")))

    # Broad standalone trivia topics (~62 topics)
    standalone_broad: list[tuple[str, str, int, str, str, str]] = [
        ("st_us_presidents", "  ?item wdt:P39 wd:Q11696 .", 5, "gen-us-president", "Name a President of the United States", "general"),
        ("st_uk_pms", "  ?item wdt:P39 wd:Q14211 .", 5, "gen-uk-pm", "Name a Prime Minister of the United Kingdom", "general"),
        ("st_roman_emp", "  ?item wdt:P39 wd:Q842606 .", 5, "gen-roman-emperor", "Name a Roman Emperor", "general"),
        ("st_popes", "  ?item wdt:P39 wd:Q19546 .", 5, "gen-pope", "Name a Pope", "general"),
        ("st_nobel_phys", "  ?item wdt:P166 wd:Q38104 .", 3, "gen-nobel-physics", "Name a Nobel Prize winner in Physics", "general"),
        ("st_nobel_chem", "  ?item wdt:P166 wd:Q44585 .", 3, "gen-nobel-chemistry", "Name a Nobel Prize winner in Chemistry", "general"),
        ("st_nobel_med", "  ?item wdt:P166 wd:Q80061 .", 3, "gen-nobel-medicine", "Name a Nobel Prize winner in Medicine", "general"),
        ("st_nobel_lit", "  ?item wdt:P166 wd:Q37922 .", 3, "gen-nobel-literature", "Name a Nobel Prize winner in Literature", "general"),
        ("st_nobel_peace", "  ?item wdt:P166 wd:Q35637 .", 3, "gen-nobel-peace", "Name a Nobel Peace Prize laureate", "general"),
        ("st_nobel_econ", "  ?item wdt:P166 wd:Q47170 .", 3, "gen-nobel-economics", "Name a Nobel Prize winner in Economics", "general"),
        ("st_astronauts", "  ?item wdt:P106 wd:Q11631 .", 5, "gen-astronaut", "Name an astronaut or cosmonaut", "general"),
        ("st_astronomers", "  ?item wdt:P106 wd:Q11063 .", 12, "gen-astronomer", "Name a famous astronomer", "general"),
        ("st_physicists", "  ?item wdt:P106 wd:Q169470 .", 15, "gen-physicist", "Name a physicist", "general"),
        ("st_chemists", "  ?item wdt:P106 wd:Q593644 .", 14, "gen-chemist", "Name a chemist", "general"),
        ("st_biologists", "  ?item wdt:P106 wd:Q864503 .", 14, "gen-biologist", "Name a biologist", "general"),
        ("st_math", "  ?item wdt:P106 wd:Q170790 .", 16, "gen-mathematician", "Name a famous mathematician", "general"),
        ("st_economists", "  ?item wdt:P106 wd:Q188094 .", 14, "gen-economist", "Name a famous economist", "general"),
        ("st_rappers", "  ?item wdt:P106 wd:Q2252262 .", 10, "gen-rapper", "Name a rapper or hip-hop artist", "general"),
        ("st_jazz", "  ?item wdt:P106 wd:Q15981151 .", 6, "gen-jazz-musician", "Name a jazz musician", "general"),
        ("st_guitarists", "  ?item wdt:P106 wd:Q855091 .", 12, "gen-guitarist", "Name a famous guitarist", "general"),
        ("st_drummers", "  ?item wdt:P106 wd:Q386854 .", 8, "gen-drummer", "Name a famous drummer", "general"),
        ("st_pianists", "  ?item wdt:P106 wd:Q486748 .", 10, "gen-pianist", "Name a famous pianist", "general"),
        ("st_musicals", "  ?item wdt:P31 wd:Q2743 .", 4, "gen-stage-musical", "Name a stage musical", "general"),
        ("st_sculptures", "  ?item wdt:P31 wd:Q860861 .", 6, "gen-sculpture", "Name a famous sculpture or statue", "general"),
        ("st_cathedrals", "  ?item wdt:P31 wd:Q2977 .", 10, "geo-cathedral", "Name a famous cathedral", "geography"),
        ("st_lighthouses", "  ?item wdt:P31 wd:Q39715 .", 4, "geo-lighthouse", "Name a famous lighthouse", "geography"),
        ("st_dams", "  ?item wdt:P31 wd:Q12323 .", 5, "geo-dam", "Name a major dam or reservoir", "geography"),
        ("st_zoos", "  ?item wdt:P31 wd:Q43501 .", 5, "geo-zoo", "Name a zoo or wildlife park", "geography"),
        ("st_themeparks", "  ?item wdt:P31 wd:Q194195 .", 3, "geo-theme-park", "Name a theme park or amusement park", "geography"),
        ("st_coasters", "  ?item wdt:P31 wd:Q204832 .", 1, "gen-roller-coaster", "Name a roller coaster", "general"),
        ("st_fastfood", "  ?item wdt:P31 wd:Q1751429 .", 2, "gen-fast-food", "Name a fast food restaurant chain", "general"),
        ("st_fashion", "  ?item wdt:P31 wd:Q1618899 .", 3, "gen-fashion-brand", "Name a fashion brand or designer label", "general"),
        ("st_carmodels", "  ?item wdt:P31 wd:Q3231690 .", 8, "gen-car-model", "Name a car model", "general"),
        ("st_os", "  ?item wdt:P31 wd:Q9135 .", 2, "gen-os", "Name a computer or mobile operating system", "general"),
        ("st_mil_air", "  ?item wdt:P31 wd:Q216916 .", 2, "gen-military-aircraft", "Name a military aircraft or fighter jet", "general"),
        ("st_warships", "  { ?item wdt:P31 wd:Q3114762 } UNION { ?item wdt:P31 wd:Q177597 } .", 4, "gen-warship", "Name a famous warship or naval vessel", "general"),
        ("st_asteroids", "  ?item wdt:P31 wd:Q3863 .", 8, "gen-asteroid", "Name a named asteroid or dwarf planet", "general"),
        ("st_comets", "  ?item wdt:P31 wd:Q3559 .", 3, "gen-comet", "Name a famous comet", "general"),
        ("st_nebulae", "  ?item wdt:P31 wd:Q42372 .", 3, "gen-nebula", "Name a nebula or star cloud", "general"),
        ("st_exoplanets", "  ?item wdt:P31 wd:Q44559 .", 3, "gen-exoplanet", "Name an exoplanet", "general"),
        ("st_vegetables", "  { ?item wdt:P31 wd:Q11004 } UNION { ?item wdt:P279 wd:Q11004 } .", 3, "gen-vegetable", "Name a vegetable", "general"),
        ("st_rocks", "  { ?item wdt:P31 wd:Q8063 } UNION { ?item wdt:P279 wd:Q8063 } .", 4, "gen-rock-type", "Name a type of rock or stone", "general"),
        ("st_softdrinks", "  ?item wdt:P31 wd:Q147538 .", 1, "gen-soft-drink", "Name a soft drink or soda brand", "general"),
        ("st_vg_franchises", "  ?item wdt:P31 wd:Q7058673 .", 3, "gen-vg-franchise", "Name a video game series or franchise", "general"),
        ("st_vg_devs", "  ?item wdt:P31 wd:Q210167 .", 6, "gen-vg-developer", "Name a video game developer or studio", "general"),
        ("st_fictional", "  ?item wdt:P31 wd:Q95074 .", 10, "gen-fictional-char", "Name a fictional character", "general"),
        ("st_vg_chars", "  ?item wdt:P31 wd:Q1569167 .", 4, "gen-vg-character", "Name a video game character", "general"),
        ("st_tennis_all", "  ?item wdt:P106 wd:Q10833314 .", 14, "spt-tennis-player", "Name a professional tennis player", "sports"),
        ("st_wrestlers", "  ?item wdt:P106 wd:Q13474373 .", 8, "spt-wrestler", "Name a professional wrestler", "sports"),
        ("st_skiers", "  ?item wdt:P106 wd:Q4144610 .", 8, "spt-skier", "Name an Olympic or alpine skier", "sports"),
        ("st_gymnasts", "  ?item wdt:P106 wd:Q15978655 .", 6, "spt-gymnast", "Name an artistic gymnast", "sports"),
        ("st_figskaters", "  ?item wdt:P106 wd:Q13219587 .", 6, "spt-figure-skater", "Name a figure skater", "sports"),
        ("st_track", "  ?item wdt:P106 wd:Q11513337 .", 12, "spt-track-athlete", "Name a track and field athlete", "sports"),
        ("st_whales", "  ?item wdt:P105 wd:Q7432 .\n  ?item wdt:P171* wd:Q160 .", 3, "gen-whale-dolphin", "Name a whale or dolphin species", "general"),
        ("st_cats_wild", "  ?item wdt:P105 wd:Q7432 .\n  ?item wdt:P171* wd:Q25265 .", 3, "gen-wild-cat", "Name a wild cat species", "general"),
        ("st_primates", "  ?item wdt:P105 wd:Q7432 .\n  ?item wdt:P171* wd:Q7380 .", 5, "gen-primate", "Name a primate species (monkey or ape)", "general"),
    ]
    broad_data: dict[str, list[dict[str, str]]] = {}
    for cache_key, where_b, min_sl, *_rest in standalone_broad:
        q = q_simple(where_b, min_sl, 3500, distinct=("UNION" in where_b))
        broad_data[cache_key] = dedup_rows_by_qid(run_sparql_cached(BROAD_V3_CACHE, cache_key, q))

    # Country-grouped natural trivia (~20 additional high-yield country facets)
    country_facets: list[tuple[str, str, str, str, int, str, str, str]] = [
        ("cf_mountains", "Q8502", "P31", "P17", 4, "geo-mtn-nat", "Name a mountain in {G}", "geography"),
        ("cf_volcanoes", "Q8072", "P31", "P17", 2, "gen-volc-nat", "Name a volcano in {G}", "general"),
        ("cf_bridges", "Q12280", "P31", "P17", 4, "gen-bridge-nat", "Name a famous bridge in {G}", "general"),
        ("cf_airports", "Q1248784", "P31", "P17", 6, "geo-airport-nat", "Name an airport in {G}", "geography"),
        ("cf_waterfalls", "Q34038", "P31", "P17", 1, "geo-fall-nat", "Name a waterfall in {G}", "geography"),
        ("cf_actors", "Q33999", "P106", "P27", 18, "gen-actor-nat", "Name an actor from {G}", "movies"),
        ("cf_directors", "Q2526255", "P106", "P27", 10, "mov-director-nat", "Name a film director from {G}", "movies"),
        ("cf_singers", "Q177220", "P106", "P27", 16, "gen-singer-nat", "Name a singer from {G}", "general"),
        ("cf_painters", "Q1028181", "P106", "P27", 10, "gen-painter-nat", "Name a painter from {G}", "general"),
        ("cf_composers", "Q36834", "P106", "P27", 8, "gen-composer-nat", "Name a composer from {G}", "general"),
        ("cf_scientists", "Q901", "P106", "P27", 12, "gen-scientist-nat", "Name a scientist from {G}", "general"),
        ("cf_philosophers", "Q4964182", "P106", "P27", 10, "gen-philosopher-nat", "Name a philosopher from {G}", "general"),
        ("cf_companies", "Q4830453", "P31", "P17", 16, "gen-company-nat", "Name a well-known company from {G}", "general"),
        ("cf_footballers", "Q937857", "P106", "P27", 25, "spt-footballer-nat", "Name a footballer from {G}", "sports"),
        ("cf_nba", "Q3665646", "P106", "P27", 8, "spt-nba-nat", "Name a basketball player from {G}", "sports"),
        ("cf_tennis", "Q10833314", "P106", "P27", 6, "spt-tennis-nat", "Name a tennis player from {G}", "sports"),
        ("cf_boxers", "Q11338576", "P106", "P27", 6, "spt-boxer-nat", "Name a boxer from {G}", "sports"),
        ("cf_cyclists", "Q2309784", "P106", "P27", 6, "spt-cyclist-nat", "Name a cyclist from {G}", "sports"),
        ("cf_swimmers", "Q10843402", "P106", "P27", 5, "spt-swimmer-nat", "Name a swimmer from {G}", "sports"),
        ("cf_cricketers", "Q12299841", "P106", "P27", 4, "spt-cricketer-nat", "Name a cricketer from {G}", "sports"),
        ("cf_olympians", "Q15243387", "P166", "P27", 6, "spt-olympian-nat", "Name an Olympic gold medalist from {G}", "sports"),
    ]
    for ckey, qid, prop, grp_prop, min_sl, *_rest in country_facets:
        q = q_grouped(f"  ?item wdt:{prop} wd:{qid} .\n  ?item wdt:{grp_prop} ?country .", "country", min_sl, 5500)
        broad_data[ckey] = dedup_rows_by_qid(run_sparql_cached(BROAD_V3_CACHE, ckey, q))

    # Video games by platform & release year/decade
    vg_platforms = [
        ("nes", "Q172742", "Nintendo Entertainment System (NES)"),
        ("snes", "Q183259", "Super Nintendo (SNES)"),
        ("n64", "Q184839", "Nintendo 64"),
        ("gamecube", "Q182172", "GameCube"),
        ("wii", "Q8079", "Wii"),
        ("switch", "Q19610114", "Nintendo Switch"),
        ("gameboy", "Q186437", "Game Boy"),
        ("gba", "Q188642", "Game Boy Advance"),
        ("nds", "Q170323", "Nintendo DS"),
        ("ps1", "Q10677", "PlayStation (PS1)"),
        ("ps2", "Q10680", "PlayStation 2"),
        ("ps3", "Q10683", "PlayStation 3"),
        ("ps4", "Q5014725", "PlayStation 4"),
        ("ps5", "Q63184502", "PlayStation 5"),
        ("xbox", "Q132020", "original Xbox"),
        ("xbox360", "Q48263", "Xbox 360"),
        ("xboxone", "Q13361286", "Xbox One"),
        ("genesis", "Q10676", "Sega Genesis / Mega Drive"),
        ("pc", "Q1406", "PC / Windows"),
        ("arcade", "Q192851", "arcade"),
    ]
    for plat_slug, pqid, _pname in vg_platforms:
        q = q_simple(f"  ?item wdt:P31 wd:Q7889 .\n  ?item wdt:P400 wd:{pqid} .", 5, 3000)
        broad_data[f"vg_plat_{plat_slug}"] = dedup_rows_by_qid(run_sparql_cached(BROAD_V3_CACHE, f"vg_plat_{plat_slug}", q))

    # Bands by genre & VG by release year
    band_genres = [
        ("rock", "Q11399", "rock"),
        ("metal", "Q38848", "heavy metal"),
        ("pop", "Q37073", "pop"),
        ("punk", "Q3071", "punk rock"),
        ("jazz", "Q8341", "jazz"),
        ("hiphop", "Q11401", "hip hop"),
        ("indie", "Q183504", "indie rock"),
        ("altrock", "Q11366", "alternative rock"),
        ("electronic", "Q9778", "electronic"),
        ("country", "Q83440", "country"),
        ("folk", "Q43343", "folk"),
        ("hardrock", "Q83270", "hard rock"),
        ("progrock", "Q49451", "progressive rock"),
        ("deathmetal", "Q483251", "death metal"),
        ("rnb", "Q45981", "R&B"),
        ("blues", "Q9759", "blues"),
    ]
    for gslug, gqid, _gname in band_genres:
        q = q_simple(f"  VALUES ?bt {{ wd:Q215380 wd:Q5741069 }}\n  ?item wdt:P31 ?bt .\n  ?item wdt:P136 wd:{gqid} .", 6, 3000, distinct=True)
        broad_data[f"band_genre_{gslug}"] = dedup_rows_by_qid(run_sparql_cached(BROAD_V3_CACHE, f"band_genre_{gslug}", q))

    # Video games by decade (via xsd:dateTime range)
    for dlabel, y0, y1 in [("1980s", 1980, 1989), ("1990s", 1990, 1999), ("2000s", 2000, 2009), ("2010s", 2010, 2019), ("2020s", 2020, 2025)]:
        q = f"""
SELECT ?item ?itemLabel (YEAR(?pub) AS ?year) ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q7889 .
  ?item wdt:P577 ?pub .
  FILTER(?pub >= "{y0}-01-01T00:00:00Z"^^xsd:dateTime && ?pub < "{y1 + 1}-01-01T00:00:00Z"^^xsd:dateTime)
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
}} LIMIT 4000""".strip()
        broad_data[f"vg_dec_{dlabel}"] = dedup_rows_by_qid(run_sparql_cached(BROAD_V3_CACHE, f"vg_dec_{dlabel}", q), keep_min_year=True)

    # Gather all high-sitelink QIDs across bands_v3 + broad_v3 + master_v2 so we can batch fetch English aliases cleanly
    all_high_qids: set[str] = set()
    for rows in list(banded_data.values()) + list(broad_data.values()) + list(master_datasets.values()):
        for r in rows:
            qid = r.get("qid")
            if qid and float(r.get("sitelinks", 1) or 1) >= 10:
                all_high_qids.add(qid)
    alias_map = fetch_wikidata_aliases(all_high_qids)

    # Assemble banded pools
    for bname, _where_b, _bands, _dist, pid, ptext, cat, upg in banded_specs:
        items = rows_to_scored(banded_data.get(bname, []), alias_map)
        if bname == "band_islands":
            items = list(CURATED_ISLANDS) + rows_to_scored(master_datasets.get("island_countries", []), alias_map) + rows_to_scored(master_datasets.get("volcanic_islands", []), alias_map) + rows_to_scored(master_datasets.get("atolls", []), alias_map) + rows_to_scored(master_datasets.get("caribbean_public", []), alias_map) + items
        if upg:
            reg.upgrade(pid, items, MAX_GLOBAL_POOL)
            if bname == "band_islands":
                reg.upgrade("geo-archipelago", items, MAX_GLOBAL_POOL)
        else:
            reg.add(pid, ptext, cat, build_balanced_tiers(items, MAX_GLOBAL_POOL))

    # Assemble standalone broad trivia
    for cache_key, _where_b, _min_sl, pid, ptext, cat in standalone_broad:
        reg.add(pid, ptext, cat, build_balanced_tiers(rows_to_scored(broad_data.get(cache_key, []), alias_map), MAX_GLOBAL_POOL))

    # Assemble VG platforms, VG decades + years, and band genres
    for plat_slug, _pqid, pname in vg_platforms:
        prep = "an" if pname[:1].lower() in {"a", "e", "i", "o"} else "a"
        reg.add(f"gen-vg-plat-{plat_slug}", f"Name {prep} {pname} video game" if plat_slug == "arcade" else f"Name a video game for {pname}", "general", build_balanced_tiers(rows_to_scored(broad_data.get(f"vg_plat_{plat_slug}", []), alias_map), MAX_FACET_ANSWERS))

    for gslug, _gqid, gname in band_genres:
        reg.add(f"gen-band-{gslug}", f"Name a {gname} band", "general", build_balanced_tiers(rows_to_scored(broad_data.get(f"band_genre_{gslug}", []), alias_map), MAX_FACET_ANSWERS))

    vg_by_year: dict[int, list[dict[str, str]]] = defaultdict(list)
    for dlabel in ["1980s", "1990s", "2000s", "2010s", "2020s"]:
        rows = broad_data.get(f"vg_dec_{dlabel}", [])
        reg.add(f"gen-vg-dec-{dlabel}", f"Name a video game from the {dlabel}", "general", build_balanced_tiers(rows_to_scored(rows, alias_map), 5000))
        for r in rows:
            ys = r.get("year", "")
            if ys.isdigit():
                y = int(ys)
                if 1985 <= y <= 2025:
                    vg_by_year[y].append(r)
    for y, yrows in sorted(vg_by_year.items()):
        if len(yrows) >= 35:
            reg.add(f"gen-vg-year-{y}", f"Name a video game released in {y}", "general", build_balanced_tiers(rows_to_scored(yrows, alias_map), MAX_FACET_ANSWERS))

    # Assemble broad master_v2 core lists, movies by country, TV by country, rivers by country, anime, manga, VG genres, animals
    master_keep_lists = [
        ("painters", "gen-painter", "Name a famous painter or artist", "general"),
        ("languages", "gen-language", "Name a world language", "general"),
        ("universities", "gen-university", "Name a university or college", "general"),
        ("museums", "gen-museum", "Name a museum", "general"),
        ("castles", "gen-castle", "Name a castle or palace", "general"),
        ("airlines", "gen-airline", "Name an airline", "general"),
        ("airports", "geo-airport", "Name an international airport", "geography"),
        ("battles", "gen-battle", "Name a historical battle", "general"),
        ("wars", "gen-war", "Name a historical war or conflict", "general"),
        ("dishes", "gen-dish", "Name a traditional dish or food", "general"),
        ("football_clubs", "spt-football-club", "Name a football (soccer) club", "sports"),
        ("nba_players", "spt-nba-player", "Name a basketball player", "sports"),
        ("baseball_players", "spt-mlb-player", "Name a baseball player", "sports"),
        ("f1_drivers", "spt-f1-driver", "Name a Formula 1 driver", "sports"),
        ("boxers", "spt-boxer", "Name a boxer", "sports"),
        ("chess_players", "spt-chess-player", "Name a chess grandmaster or player", "sports"),
        ("golfers_v2", "spt-golfer", "Name a professional golfer", "sports"),
        ("nfl_players", "spt-nfl-player", "Name an American football (NFL) player", "sports"),
        ("nhl_players", "spt-nhl-player", "Name an ice hockey (NHL) player", "sports"),
        ("swimmers", "spt-swimmer", "Name a competitive swimmer", "sports"),
        ("cyclists", "spt-cyclist", "Name a professional cyclist", "sports"),
        ("cricketers", "spt-cricketer", "Name a cricketer", "sports"),
        ("philosophers", "gen-philosopher", "Name a philosopher", "general"),
        ("architects", "gen-architect", "Name a famous architect", "general"),
        ("inventors", "gen-inventor", "Name an inventor", "general"),
        ("explorers", "gen-explorer", "Name a famous explorer", "general"),
        ("monarchs", "gen-monarch", "Name a monarch, king, or queen", "general"),
        ("companies", "gen-company", "Name a well-known company or corporation", "general"),
        ("websites", "gen-website", "Name a website or online platform", "general"),
        ("spacecraft", "gen-spacecraft", "Name a spacecraft or space probe", "general"),
        ("stars", "gen-star", "Name a star in the night sky", "general"),
        ("compounds", "gen-compound", "Name a chemical compound or molecule", "general"),
        ("diseases", "gen-disease", "Name a medical disease or condition", "general"),
        ("cat_breeds", "gen-cat-breed", "Name a cat breed", "general"),
        ("horse_breeds", "gen-horse-breed", "Name a horse breed", "general"),
        ("breads", "gen-bread", "Name a type of bread", "general"),
        ("soups", "gen-soup", "Name a soup or stew", "general"),
        ("sauces", "gen-sauce", "Name a sauce or condiment", "general"),
        ("pastries", "gen-pastry", "Name a pastry or baked sweet", "general"),
        ("wine_grapes", "gen-grape", "Name a wine grape variety", "general"),
        ("comics_chars", "gen-comic-char", "Name a comic book character", "general"),
        ("skyscrapers", "geo-skyscraper", "Name a skyscraper or tall tower", "geography"),
        ("glaciers", "geo-glacier", "Name a glacier", "geography"),
        ("caves", "geo-cave", "Name a cave or cavern", "geography"),
        ("canyons", "geo-canyon", "Name a canyon or gorge", "geography"),
        ("bays", "geo-bay", "Name a bay or gulf", "geography"),
        ("capes", "geo-cape", "Name a cape or headland", "geography"),
        ("nobel_laureates", "gen-nobel", "Name a Nobel Prize laureate", "general"),
        ("anime_series", "gen-anime", "Name an anime series", "general"),
        ("manga_series", "gen-manga", "Name a manga series", "general"),
        ("mammals_en", "gen-mammal", "Name a mammal species", "general"),
        ("birds_en", "gen-bird", "Name a bird species", "general"),
        ("reptiles_en", "gen-reptile", "Name a reptile species", "general"),
        ("fishes_en", "gen-fish", "Name a fish species", "general"),
    ]
    for cache_k, pid, ptext, cat in master_keep_lists:
        rows = master_datasets.get(cache_k, [])
        reg.add(pid, ptext, cat, build_balanced_tiers(rows_to_scored(rows, alias_map), MAX_GLOBAL_POOL))

    for gid, gname in [("rpg", "role-playing (RPG)"), ("fps", "first-person shooter"), ("platformer", "platformer"), ("strategy", "strategy"), ("racing", "racing"), ("fighting", "fighting"), ("horror", "survival horror")]:
        reg.add(f"gen-vg-{gid}", f"Name a {gname} video game", "general", build_balanced_tiers(rows_to_scored(master_datasets.get(f"vg_genre_{gid}", []), alias_map), MAX_FACET_ANSWERS))

    # Movies by country + TV by country + Rivers by country
    for cid, adj in [("france", "French"), ("japan", "Japanese"), ("uk", "British"), ("italy", "Italian"), ("germany", "German"), ("india", "Indian"), ("korea", "South Korean"), ("spain", "Spanish"), ("canada", "Canadian"), ("australia", "Australian"), ("sweden", "Swedish"), ("mexico", "Mexican"), ("china", "Chinese"), ("russia", "Russian"), ("brazil", "Brazilian")]:
        reg.add(f"mov-country-{cid}", f"Name a {adj} movie", "movies", build_balanced_tiers(rows_to_scored(master_datasets.get(f"film_country_{cid}", []), alias_map), MAX_FACET_ANSWERS))

    for code, adj in [("us", "American"), ("uk", "British"), ("jp", "Japanese"), ("kr", "South Korean"), ("ca", "Canadian")]:
        reg.add(f"gen-tv-{code}", f"Name a {adj} TV show", "general", build_balanced_tiers(rows_to_scored(master_datasets.get(f"tv_{code}", []), alias_map), MAX_FACET_ANSWERS))

    for code, cname in [("usa", "the United States"), ("russia", "Russia"), ("canada", "Canada"), ("brazil", "Brazil"), ("china", "China"), ("france", "France"), ("germany", "Germany"), ("uk", "the United Kingdom"), ("australia", "Australia"), ("india", "India")]:
        reg.add(f"geo-riv-{code}", f"Name a river in {cname}", "geography", build_balanced_tiers(rows_to_scored(master_datasets.get(f"rivers_{code}", []), alias_map), MAX_FACET_ANSWERS))

    # Upgrade seed prompts with deep pools
    for mkey, pid in [
        ("national_parks_world", "geo-national-park"),
        ("landmarks_world", "geo-landmark"),
        ("mountain_ranges_world", "geo-mountain-range"),
        ("waterfalls_world", "geo-waterfall"),
        ("deserts_world", "geo-desert"),
        ("volcanoes_world", "gen-volcano"),
        ("bridges_world", "gen-bridge"),
        ("stadiums_world", "spt-stadium"),
        ("paintings_deep", "gen-painting"),
        ("music_genres_deep", "gen-music-genre"),
        ("board_games_deep", "gen-board-game"),
        ("superheroes_deep", "gen-superhero"),
    ]:
        reg.upgrade(pid, rows_to_scored(master_datasets.get(mkey, []), alias_map), MAX_GLOBAL_POOL)

    # Helper for country-grouped Wikidata rows
    def emit_country_groups(rows: list[dict[str, str]], grp_key: str, id_pref: str, prompt_fmt: str, cat: str, min_items: int = 30) -> None:
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            g = r.get(grp_key, "").strip()
            if g and not re.match(r"^Q\d+$", g):
                buckets[g].append(r)
        for grp, grp_rows in sorted(buckets.items()):
            items = rows_to_scored(grp_rows, alias_map)
            if len(items) < min_items:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", grp.lower()).strip("-")
            reg.add(f"{id_pref}-{slug}", prompt_fmt.format(G=grp), cat, build_balanced_tiers(items, MAX_FACET_ANSWERS))

    # Reuse master_v2 people/places by country + all new broad_v3 country_facets
    for mkey, id_pref, fmt, cat in [
        ("authors_country", "gen-author-nat", "Name an author from {G}", "general"),
        ("bands_country", "gen-band-nat", "Name a band from {G}", "general"),
        ("clubs_country", "spt-club-nat", "Name a football club in {G}", "sports"),
        ("stadiums_country", "spt-stad-nat", "Name a sports stadium in {G}", "sports"),
        ("islands_country", "geo-isl-nat", "Name an island in {G}", "geography"),
        ("lakes_country", "geo-lak-nat", "Name a lake in {G}", "geography"),
        ("parks_country", "geo-prk-nat", "Name a national park in {G}", "geography"),
        ("unesco_country", "geo-her-nat", "Name a World Heritage Site in {G}", "geography"),
        ("dishes_country", "gen-dish-nat", "Name a traditional food or dish from {G}", "general"),
        ("universities_country", "gen-uni-nat", "Name a university in {G}", "general"),
        ("museums_country", "gen-mus-nat", "Name a museum in {G}", "general"),
        ("castles_country", "gen-cas-nat", "Name a castle or palace in {G}", "general"),
    ]:
        emit_country_groups(master_datasets.get(mkey, []), "grpLabel", id_pref, fmt, cat, min_items=32)

    for ckey, _qid, _prop, _grp, _sl, id_pref, fmt, cat in country_facets:
        emit_country_groups(broad_data.get(ckey, []), "countryLabel", id_pref, fmt, cat, min_items=30)


def write_sqlite_and_chunks(reg: PromptRegistry) -> tuple[int, int, int]:
    if SQLITE_OUT_PATH.exists():
        SQLITE_OUT_PATH.unlink()
    conn = sqlite3.connect(SQLITE_OUT_PATH)
    conn.execute("PRAGMA page_size = 4096")
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = MEMORY")

    conn.executescript("""
        CREATE TABLE prompts (
          id INTEGER PRIMARY KEY,
          slug TEXT UNIQUE NOT NULL,
          text TEXT NOT NULL,
          category TEXT NOT NULL,
          form_level INTEGER NOT NULL,
          pack_only INTEGER NOT NULL,
          answer_count INTEGER NOT NULL
        );
        CREATE TABLE entities (
          id INTEGER PRIMARY KEY,
          canonical TEXT NOT NULL
        );
        CREATE TABLE entity_forms (
          norm TEXT NOT NULL,
          entity_id INTEGER NOT NULL,
          form_kind INTEGER NOT NULL,
          PRIMARY KEY (norm, entity_id)
        ) WITHOUT ROWID;
        CREATE TABLE prompt_answers (
          prompt_id INTEGER NOT NULL,
          entity_id INTEGER NOT NULL,
          tier INTEGER NOT NULL,
          rank INTEGER NOT NULL,
          p3 TEXT NOT NULL,
          s3 TEXT NOT NULL,
          PRIMARY KEY (prompt_id, entity_id)
        ) WITHOUT ROWID;
    """)

    entity_id_by_canon: dict[str, int] = {}
    next_eid = 1

    # Track entity_forms cleanly using lowest form_kind priority (0 < 1 < 2)
    forms_dict: dict[tuple[str, int], int] = {}

    def record_form(norm: str, eid: int, kind: int) -> None:
        if not norm:
            return
        k = (norm, eid)
        prev = forms_dict.get(k)
        if prev is None or kind < prev:
            forms_dict[k] = kind

    prompt_rows: list[tuple[int, str, str, str, int, int, int]] = []
    pa_rows: list[tuple[int, int, int, int, str, str]] = []
    total_answers = 0

    for db_pid, p in enumerate(reg.prompts, start=1):
        pid = p["id"]
        flevel = prompt_form_level(pid, p["category"])
        pack_only = 1 if p.get("packOnly") else 0
        prompt_rows.append((db_pid, pid, p["text"], p["category"], flevel, pack_only, p["answerCount"]))
        p["dbId"] = db_pid
        p["formLevel"] = flevel

        rank = 0
        for tier_idx, tier_name in enumerate(TIERS):
            for entry in p["tiers"][tier_name]:
                if isinstance(entry, str):
                    canon, aliases = entry, []
                else:
                    canon, aliases = entry[0], entry[1:]

                eid = entity_id_by_canon.get(canon)
                if eid is None:
                    eid = next_eid
                    next_eid += 1
                    entity_id_by_canon[canon] = eid

                cnorm = normalize_answer(canon)
                if not cnorm:
                    continue
                stripped_canon = strip_article(cnorm) or cnorm
                p3 = stripped_canon[:3] if rank < 3000 else ""
                s3 = stripped_canon[-3:] if rank < 3000 else ""
                pa_rows.append((db_pid, eid, tier_idx, rank, p3, s3))
                rank += 1
                total_answers += 1

                # form_kind = 0: canonical exact / plural / Roman / abbreviation variants
                for v in plural_variants(cnorm):
                    record_form(v, eid, 0)
                if flevel >= 1:
                    r_cnorm = normalize_roman_numerals(cnorm)
                    if r_cnorm != cnorm:
                        for v in plural_variants(r_cnorm):
                            record_form(v, eid, 0)
                    a_cnorm = expand_abbreviations(cnorm)
                    if a_cnorm != cnorm:
                        for v in plural_variants(a_cnorm):
                            record_form(v, eid, 0)

                    # form_kind = 1: aliases + category affixes + subtitles
                    for al in aliases:
                        anorm = normalize_answer(al)
                        if anorm:
                            for v in plural_variants(anorm):
                                record_form(v, eid, 1)
                            r_al = normalize_roman_numerals(anorm)
                            if r_al != anorm:
                                record_form(r_al, eid, 1)
                            a_al = expand_abbreviations(anorm)
                            if a_al != anorm:
                                record_form(a_al, eid, 1)

                    for core in strip_category_affixes(cnorm):
                        for v in plural_variants(core):
                            record_form(v, eid, 1)
                    for sub in extract_subtitle_variants(canon):
                        record_form(sub, eid, 1)

                # form_kind = 2: person surname(s) for person prompts
                if flevel == 2:
                    for sname in extract_person_surnames(canon):
                        record_form(sname, eid, 2)

    print(f"  [SQLite] Inserting {len(prompt_rows):,} prompts, {len(entity_id_by_canon):,} entities, {len(pa_rows):,} prompt_answers, {len(forms_dict):,} entity_forms...")
    conn.executemany("INSERT INTO prompts VALUES (?, ?, ?, ?, ?, ?, ?)", prompt_rows)
    conn.executemany("INSERT INTO entities VALUES (?, ?)", ((eid, canon) for canon, eid in entity_id_by_canon.items()))
    conn.executemany("INSERT INTO entity_forms VALUES (?, ?, ?)", ((n, eid, k) for (n, eid), k in forms_dict.items()))
    conn.executemany("INSERT INTO prompt_answers VALUES (?, ?, ?, ?, ?, ?)", pa_rows)

    print("  [SQLite] Building B-tree indexes and vacuuming...")
    conn.executescript("""
        CREATE INDEX idx_pa_browse ON prompt_answers(prompt_id, tier, rank);
        CREATE INDEX idx_pa_p3 ON prompt_answers(prompt_id, p3, rank) WHERE rank < 3000;
        CREATE INDEX idx_pa_s3 ON prompt_answers(prompt_id, s3, rank) WHERE rank < 3000;
        ANALYZE;
        VACUUM;
    """)
    conn.close()

    db_size = SQLITE_OUT_PATH.stat().st_size
    print(f"  [SQLite] Cached database size: {db_size / (1024 * 1024):.2f} MiB ({db_size:,} bytes)")
    return db_size, len(forms_dict)


def write_manifest_and_packs(reg: PromptRegistry, total_answers: int) -> tuple[int, int]:
    packs_meta = [
        ("words", "WORDS & LANGUAGE", "English quirks, loanwords, and lexicon trivia", "chapters", "#38bdf8",
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

    manifest_entries = []
    daily_eligible = 0
    for p in reg.prompts:
        entry: dict[str, Any] = {
            "id": p["id"],
            "text": p["text"],
            "category": p["category"],
            "answerCount": p["answerCount"],
            "dbId": p["dbId"],
            "formLevel": p["formLevel"],
        }
        if p.get("packOnly"):
            entry["packOnly"] = True
        else:
            daily_eligible += 1
        manifest_entries.append(entry)

    year_days = daily_eligible // 7
    manifest_ts = (
        "// Auto-generated by scripts/build_sqlite_database.py\n"
        "import type { PromptMeta, ThemedPack } from '../domain/types';\n\n"
        f"export const TOTAL_ANSWER_COUNT = {total_answers};\n\n"
        f"export const YEAR_COVERAGE_DAYS = {year_days};\n\n"
        f"export const PROMPT_MANIFEST: PromptMeta[] = {json.dumps(manifest_entries, separators=(',', ':'))};\n\n"
        f"export const THEMED_PACKS: ThemedPack[] = {json.dumps(themed_packs, indent=2)};\n"
    )
    OUT_MANIFEST_PATH.write_text(manifest_ts, encoding="utf-8")
    return daily_eligible, year_days


def main() -> None:
    t0 = time.time()
    reg = PromptRegistry()

    print("1. Loading 159 curated seed prompts (7 letter-constrained word prompts marked packOnly)...")
    load_seed_159(reg)
    print(f"   Loaded {len(reg.prompts)} curated seeds.")

    print("2. Downloading/verifying bulk open datasets (GeoNames + IMDb)...")
    c_zip, c_info, a1, i_rat, i_bas = download_bulk_datasets()

    print("3. Processing GeoNames world/country/state/region cities...")
    process_geonames_bulk(reg, c_zip, c_info, a1)
    print(f"   Prompts so far: {len(reg.prompts)}")

    print("4. Processing IMDb movies & TV series...")
    process_imdb_bulk(reg, i_rat, i_bas)
    print(f"   Prompts so far: {len(reg.prompts)}")

    print("5. Fetching sitelink-banded & broad trivia Wikidata datasets...")
    run_wikidata_batches_and_broad(reg)
    print(f"   Total broad prompts assembled: {len(reg.prompts)}")

    print("6. Building local SQLite cache and exporting Zero-Range Hybrid Static Shards...")
    total_answers = sum(p["answerCount"] for p in reg.prompts)
    db_size, total_forms = write_sqlite_and_chunks(reg)
    from export_static_shards import export_from_sqlite

    shard_stats = export_from_sqlite(SQLITE_OUT_PATH)
    daily_eligible = shard_stats["daily_eligible"]
    year_days = shard_stats["year_days"]

    cat_counts = Counter(p["category"] for p in reg.prompts if not p.get("packOnly"))
    print("\n=== KRILLION ZERO-RANGE BUILD COMPLETE ===")
    print(f"Elapsed: {time.time() - t0:.1f}s")
    print(f"Total prompts: {len(reg.prompts):,} ({daily_eligible:,} daily-eligible -> {year_days} non-repeating days!)")
    print(f"Daily-eligible by category: {dict(cat_counts)}")
    print(f"Total prompt-answer links: {total_answers:,} | Total searchable normalized forms: {total_forms:,}")
    print(
        f"Cached SQLite: {db_size / (1024 * 1024):.2f} MiB | "
        f"Static JSON shards: {shard_stats['total_raw_mib']:.2f} MiB across {shard_stats['total_files']} files"
    )
    for pid in ["geo-world-city", "mov-any-movie", "gen-tv-show", "geo-island", "geo-river", "geo-mountain", "gen-song", "gen-band", "gen-book", "gen-video-game", "mov-director", "gen-composer", "spt-footballer", "geo-city-am-usa"]:
        p = reg.by_id.get(pid)
        print(f"  [MegaCheck] {pid}: {p['answerCount'] if p else 'MISSING':,}")


if __name__ == "__main__":
    main()
