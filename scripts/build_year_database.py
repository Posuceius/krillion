#!/usr/bin/env python3
"""
Build a 3,600+ prompt Krillion database (500+ consecutive non-repeating days)
from:
  1. All 159 core curated & Wikidata-enriched prompts (with island/archipelago & movie fixes)
  2. Letter-slices of large core & master Wikidata pools
  3. Fast cached master Wikidata SPARQL datasets (TV, anime, manga, songs, video games,
     movies by genre/decade/country, Americas/world cities, rivers, sports, science, nature,
     history, companies, foods)
  4. Rich English wordcraft prompts derived from /usr/share/dict/ + Norvig 333k word frequencies

Outputs:
  - public/data/chunks/chunk-000.json .. chunk-127.json (128 deterministic chunks)
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
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
MASTER_CACHE = CACHE_DIR / "master"
ENRICHED_159_DIR = CACHE_DIR / "enriched_159"
WORD_FREQ_PATH = CACHE_DIR / "word_freq.txt"
OLD_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
OUT_CHUNKS_DIR = ROOT / "public" / "data" / "chunks"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

NUM_CHUNKS = 128
TIERS = ["plankton", "tooclever", "schooler", "rare", "deepcut", "krillion"]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "KrillionStaticBuilder/1.2 (https://gitlab.com; static-pages-game)"
MIN_ANSWERS = 30
MAX_FACET_ANSWERS = 1200
MAX_SEED_ANSWERS = 3500


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
    if len(label) > 50 or not re.search(r"[a-zA-Z]", label):
        return None
    aliases: list[str] = []
    m = re.match(r"^(.+?)\s*\([^)]{2,28}\)$", label)
    if m:
        short = m.group(1).strip()
        if len(short) >= 2:
            aliases.append(label)
            label = short
    return label, aliases


def first_alpha_letter(s: str) -> str | None:
    s = strip_article(normalize_answer(s))
    if not s:
        return None
    ch = s[0]
    return ch.upper() if "a" <= ch <= "z" else None


def run_sparql_rows(name: str, query: str) -> list[dict[str, str]]:
    MASTER_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = MASTER_CACHE / f"{name}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text("utf-8"))
        if len(data) > 0:
            return data

    url = f"{SPARQL_ENDPOINT}?{urllib.parse.urlencode({'query': query})}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": USER_AGENT,
        },
    )

    for attempt in range(2):
        try:
            time.sleep(0.5 * (attempt + 1))
            with urllib.request.urlopen(req, timeout=14) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rows: list[dict[str, str]] = []
            for b in payload.get("results", {}).get("bindings", []):
                row = {k: v.get("value", "") for k, v in b.items()}
                lbl = row.get("itemLabel", "")
                if not lbl or re.match(r"^Q\d+$", lbl):
                    continue
                rows.append(row)
            if rows:
                cache_file.write_text(json.dumps(rows), encoding="utf-8")
            print(f"  [SPARQL] {name}: {len(rows)} rows")
            return rows
        except Exception as exc:
            print(f"  [SPARQL retry {attempt+1}] {name}: {exc}")
            time.sleep(1.2 * (attempt + 1))

    return []


def build_balanced_tiers(
    scored_items: list[tuple[str, float, list[str]]],
    max_answers: int = MAX_FACET_ANSWERS,
) -> dict[str, list[Any]] | None:
    ordered = sorted(scored_items, key=lambda x: x[1], reverse=True)
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
        for al in aliases:
            anorm = normalize_answer(al)
            if not anorm:
                continue
            avars = plural_variants(anorm)
            if any(v in seen_norms or v in new_vars for v in avars):
                continue
            valid_aliases.append(al)
            new_vars.extend(avars)
        for v in new_vars:
            seen_norms.add(v)
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
    """Preserve base seed/enriched items at their tiers, and append new verified items."""
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

    def upgrade(self, pid: str, additions: list[tuple[str, float, list[str]]], max_total: int = MAX_SEED_ANSWERS) -> None:
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


def deepen_islands_and_archipelagos(reg: PromptRegistry) -> None:
    """Ensure Bonaire, Aruba, Curacao, island countries, atolls, volcanic islands, and Caribbean entities are all included."""
    island_queries = [
        ("island_countries", "Q112099", 1),
        ("atolls", "Q42523", 2),
        ("volcanic_islands", "Q1161182", 2),
        ("caribbean_public", "Q3237519", 1),
        ("island_groups", "Q1402592", 2),
    ]
    extra_islands: list[tuple[str, float, list[str]]] = list(CURATED_ISLANDS)
    for name, qid, min_sl in island_queries:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 1200"""
        for r in run_sparql_rows(name, q):
            c = clean_label(r["itemLabel"])
            if c:
                extra_islands.append((c[0], float(r.get("sitelinks", 1) or 1), c[1]))

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


def enrich_from_master_wikidata(reg: PromptRegistry) -> int:
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
        buckets: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
        for r in rows:
            grp = r.get(group_key, "").strip()
            if not grp or re.match(r"^Q\d+$", grp):
                continue
            cleaned = clean_label(r["itemLabel"])
            if not cleaned:
                continue
            canon, aliases = cleaned
            sl = float(r.get("sitelinks", 1) or 1)
            buckets[grp].append((canon, sl, aliases))

        for grp, items in sorted(buckets.items()):
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
        buckets: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
        for r in rows:
            cleaned = clean_label(r["itemLabel"])
            if not cleaned:
                continue
            canon, aliases = cleaned
            ltr = first_alpha_letter(canon)
            if ltr:
                sl = float(r.get("sitelinks", 1) or 1)
                buckets[ltr].append((canon, sl, aliases))
        for ltr, items in sorted(buckets.items()):
            if len(items) < MIN_ANSWERS:
                continue
            if reg.add(
                f"{id_prefix}-ltr-{ltr.lower()}",
                prompt_fmt.format(L=ltr),
                category,
                build_balanced_tiers(items),
            ):
                added += 1

    # 1. Cities by continent, country, and Americas/major countries
    continents = [
        ("eu", "Q46", "European", 10),
        ("as", "Q48", "Asian", 10),
        ("af", "Q15", "African", 6),
        ("oc", "Q55643", "Oceanian", 3),
    ]
    all_cities: list[dict[str, str]] = []
    for code, qid, cname, min_sl in continents:
        q = f"""
SELECT ?itemLabel ?countryLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 2800"""
        rows = run_sparql_rows(f"cities_{code}", q)
        all_cities.extend(rows)
        add_group_slices(rows, "countryLabel", f"geo-city-{code}", "Name a city in {G}", "geography")
        add_letter_slices(rows, f"geo-city-{code}", f"Name a {cname} city starting with the letter {{L}}", "geography")

    # Fast per-country Americas cities (fixes cities_na / cities_sa timeouts!)
    americas_countries = [
        ("usa", "Q30", "the United States", 10),
        ("canada", "Q16", "Canada", 4),
        ("mexico", "Q96", "Mexico", 6),
        ("brazil", "Q155", "Brazil", 6),
        ("argentina", "Q414", "Argentina", 5),
        ("colombia", "Q739", "Colombia", 4),
        ("peru", "Q419", "Peru", 4),
        ("chile", "Q298", "Chile", 4),
    ]
    for code, qid, cname, min_sl in americas_countries:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 1600"""
        rows = run_sparql_rows(f"cities_am_{code}", q)
        all_cities.extend(rows)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(f"geo-city-am-{code}", f"Name a city in {cname}", "geography", build_balanced_tiers(items))
        add_letter_slices(rows, f"geo-city-am-{code}", f"Name a city in {cname} starting with the letter {{L}}", "geography")

    # U.S. cities by state
    us_states_q = """
SELECT ?itemLabel ?stateLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q1093829 .
  ?item wdt:P131 ?state .
  ?state wdt:P31 wd:Q35657 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 3500"""
    us_cities = run_sparql_rows("us_cities_by_state", us_states_q)
    add_group_slices(us_cities, "stateLabel", "geo-us-city", "Name a city in {G}", "geography")
    add_letter_slices(all_cities, "geo-world-city", "Name a world city starting with the letter {L}", "geography")

    # Fast per-country rivers (fixes rivers_country timeout!)
    river_countries = [
        ("usa", "Q30", "the United States", 8),
        ("russia", "Q159", "Russia", 8),
        ("canada", "Q16", "Canada", 6),
        ("brazil", "Q155", "Brazil", 6),
        ("china", "Q148", "China", 6),
        ("france", "Q142", "France", 6),
        ("germany", "Q183", "Germany", 6),
        ("uk", "Q145", "the United Kingdom", 6),
        ("australia", "Q408", "Australia", 5),
        ("india", "Q668", "India", 6),
    ]
    for code, qid, cname, min_sl in river_countries:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q4022 .
  ?item wdt:P17 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 800"""
        rows = run_sparql_rows(f"rivers_{code}", q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(f"geo-riv-{code}", f"Name a river in {cname}", "geography", build_balanced_tiers(items))

    # 2. Films by decade, year, genre, genre x decade, country, letter
    film_decades = [
        ("1940s", 1940, 1949, 10),
        ("1960s", 1960, 1969, 14),
        ("1970s", 1970, 1979, 14),
        ("1980s", 1980, 1989, 16),
        ("1990s", 1990, 1999, 18),
        ("2000s", 2000, 2009, 20),
        ("2010s", 2010, 2019, 20),
        ("2020s", 2020, 2025, 16),
    ]
    all_films: list[dict[str, str]] = []
    decade_film_norms: dict[str, dict[str, tuple[str, float, list[str]]]] = {}

    for dlabel, y0, y1, min_sl in film_decades:
        q = f"""
SELECT ?itemLabel (YEAR(?pub) AS ?year) ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P577 ?pub .
  FILTER(?pub >= "{y0}-01-01T00:00:00Z"^^xsd:dateTime && ?pub < "{y1 + 1}-01-01T00:00:00Z"^^xsd:dateTime)
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 2800"""
        rows = run_sparql_rows(f"films_{dlabel}", q)
        all_films.extend(rows)
        dec_items = []
        dmap: dict[str, tuple[str, float, list[str]]] = {}
        for r in rows:
            c = clean_label(r["itemLabel"])
            if c:
                sl = float(r.get("sitelinks", 1) or 1)
                dec_items.append((c[0], sl, c[1]))
                dmap[normalize_answer(c[0])] = (c[0], sl, c[1])
        decade_film_norms[dlabel] = dmap
        reg.add(f"mov-decade-{dlabel}", f"Name a movie from the {dlabel}", "movies", build_balanced_tiers(dec_items))
        add_group_slices(rows, "year", "mov-year", "Name a movie released in {G}", "movies", min_group=35)
        add_letter_slices(rows, f"mov-{dlabel}", f"Name a {dlabel} movie starting with the letter {{L}}", "movies")

    add_letter_slices(all_films, "mov-all", "Name a movie starting with the letter {L}", "movies")
    one_word_films = [
        r for r in all_films
        if (c := clean_label(r["itemLabel"])) and " " not in c[0] and "-" not in c[0]
    ]
    one_word_items = [
        (c[0], float(r.get("sitelinks", 1) or 1), c[1])
        for r in one_word_films
        if (c := clean_label(r["itemLabel"]))
    ]
    reg.upgrade("mov-one-word", one_word_items, MAX_SEED_ANSWERS)
    add_letter_slices(one_word_films, "mov-oneword", "Name a one-word movie starting with the letter {L}", "movies")

    film_genres = [
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
    genre_film_norms: dict[str, tuple[str, dict[str, tuple[str, float, list[str]]]]] = {}
    for gid, qid, gname in film_genres:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 2200"""
        rows = run_sparql_rows(f"film_genre_{gid}", q)
        items = []
        gmap: dict[str, tuple[str, float, list[str]]] = {}
        for r in rows:
            c = clean_label(r["itemLabel"])
            if c:
                sl = float(r.get("sitelinks", 1) or 1)
                items.append((c[0], sl, c[1]))
                gmap[normalize_answer(c[0])] = (c[0], sl, c[1])
        genre_film_norms[gid] = (gname, gmap)
        reg.add(f"mov-genre-{gid}", f"Name a {gname} movie", "movies", build_balanced_tiers(items))
        add_letter_slices(rows, f"mov-genre-{gid}", f"Name a {gname} movie starting with the letter {{L}}", "movies")

    # Deepen mov-90s-comedy and generate Genre x Decade intersections (zero network!)
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

    # Films by country
    film_countries = [
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
    for cid, qid, adj in film_countries:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P495 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 1600"""
        rows = run_sparql_rows(f"film_country_{cid}", q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(f"mov-country-{cid}", f"Name a {adj} movie", "movies", build_balanced_tiers(items))
        add_letter_slices(rows, f"mov-country-{cid}", f"Name a {adj} movie starting with the letter {{L}}", "movies")

    # 3. TV Series (fixed Q5398426!), Anime, Manga, Songs, Video Game genres, Fictional Characters
    tv_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q5398426 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 14)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2800"""
    tv_rows = run_sparql_rows("tv_series_v2", tv_q)
    tv_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in tv_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-tv-show", "Name a TV show or series", "general", build_balanced_tiers(tv_items, MAX_SEED_ANSWERS))
    add_letter_slices(tv_rows, "gen-tv", "Name a TV show starting with the letter {L}", "general")

    # TV series by country
    for code, qid, adj in [
        ("us", "Q30", "American"),
        ("uk", "Q145", "British"),
        ("jp", "Q17", "Japanese"),
        ("kr", "Q884", "South Korean"),
        ("ca", "Q16", "Canadian"),
    ]:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q5398426 .
  ?item wdt:P495 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 12)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 1600"""
        rows = run_sparql_rows(f"tv_{code}", q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(f"gen-tv-{code}", f"Name a {adj} TV show", "general", build_balanced_tiers(items))

    # Anime & Manga
    anime_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q63952888 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800"""
    anime_rows = run_sparql_rows("anime_series", anime_q)
    anime_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in anime_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-anime", "Name an anime series", "general", build_balanced_tiers(anime_items, MAX_SEED_ANSWERS))
    add_letter_slices(anime_rows, "gen-anime", "Name an anime series starting with the letter {L}", "general")

    manga_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q21198342 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800"""
    manga_rows = run_sparql_rows("manga_series", manga_q)
    manga_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in manga_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-manga", "Name a manga series", "general", build_balanced_tiers(manga_items, MAX_SEED_ANSWERS))
    add_letter_slices(manga_rows, "gen-manga", "Name a manga series starting with the letter {L}", "general")

    # Hit Singles / Songs
    songs_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q134556 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 18)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2600"""
    song_rows = run_sparql_rows("hit_songs", songs_q)
    song_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in song_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-song", "Name a famous song or single", "general", build_balanced_tiers(song_items, MAX_SEED_ANSWERS))
    add_letter_slices(song_rows, "gen-song", "Name a famous song starting with the letter {L}", "general")

    # Video games + subgenres
    vg_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q7889 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 16)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2800"""
    vg_rows = run_sparql_rows("video_games", vg_q)
    vg_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in vg_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-video-game", "Name a video game", "general", build_balanced_tiers(vg_items, MAX_SEED_ANSWERS))
    add_letter_slices(vg_rows, "gen-vg", "Name a video game starting with the letter {L}", "general")

    vg_genres = [
        ("rpg", "Q744038", "role-playing (RPG)"),
        ("fps", "Q185029", "first-person shooter"),
        ("platformer", "Q828322", "platformer"),
        ("strategy", "Q472285", "strategy"),
        ("racing", "Q860750", "racing"),
        ("fighting", "Q744038", "fighting"),
        ("horror", "Q223251", "survival horror"),
    ]
    vg_genres[5] = ("fighting", "Q343568", "fighting")
    for gid, qid, gname in vg_genres:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P31 wd:Q7889 .
  ?item wdt:P136 wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 1200"""
        rows = run_sparql_rows(f"vg_genre_{gid}", q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(f"gen-vg-{gid}", f"Name a {gname} video game", "general", build_balanced_tiers(items))

    # 4. Master lists: Literature, Arts, Music, History, Science, Nature, Tech, Sports
    master_lists = [
        ("books", "Q7725634", "P31", 15, "gen-book", "Name a famous book or novel", "general"),
        ("actors", "Q33999", "P106", 35, "mov-actor", "Name a film or TV actor", "movies"),
        ("painters", "Q1028181", "P106", 20, "gen-painter", "Name a famous painter or artist", "general"),
        ("bands", "Q215380", "P31", 22, "gen-band", "Name a musical band or group", "general"),
        ("singers", "Q177220", "P106", 32, "gen-singer", "Name a singer or vocalist", "general"),
        ("albums", "Q482994", "P31", 16, "gen-album", "Name a studio album", "general"),
        ("languages", "Q34770", "P31", 15, "gen-language", "Name a world language", "general"),
        ("universities", "Q3918", "P31", 25, "gen-university", "Name a university or college", "general"),
        ("museums", "Q33506", "P31", 14, "gen-museum", "Name a museum", "general"),
        ("castles", "Q23413", "P31", 10, "gen-castle", "Name a castle or palace", "general"),
        ("airlines", "Q46970", "P31", 10, "gen-airline", "Name an airline", "general"),
        ("airports", "Q1248784", "P31", 18, "geo-airport", "Name an international airport", "geography"),
        ("battles", "Q178561", "P31", 18, "gen-battle", "Name a historical battle", "general"),
        ("wars", "Q198", "P31", 18, "gen-war", "Name a historical war or conflict", "general"),
        ("dishes", "Q746549", "P31", 6, "gen-dish", "Name a traditional dish or food", "general"),
        ("football_clubs", "Q476028", "P31", 20, "spt-football-club", "Name a football (soccer) club", "sports"),
        ("nba_players", "Q3665646", "P106", 20, "spt-nba-player", "Name a basketball player", "sports"),
        ("baseball_players", "Q10871364", "P106", 22, "spt-mlb-player", "Name a baseball player", "sports"),
        ("f1_drivers", "Q10841764", "P106", 12, "spt-f1-driver", "Name a Formula 1 driver", "sports"),
        ("boxers", "Q11338576", "P106", 15, "spt-boxer", "Name a boxer", "sports"),
        ("chess_players", "Q10873124", "P106", 12, "spt-chess-player", "Name a chess grandmaster or player", "sports"),
        # New rich non-pop-culture categories:
        ("golfers_v2", "Q490253", "P106", 10, "spt-golfer", "Name a professional golfer", "sports"),
        ("nfl_players", "Q19204627", "P106", 16, "spt-nfl-player", "Name an American football (NFL) player", "sports"),
        ("nhl_players", "Q11774891", "P106", 16, "spt-nhl-player", "Name an ice hockey (NHL) player", "sports"),
        ("swimmers", "Q10843402", "P106", 12, "spt-swimmer", "Name a competitive swimmer", "sports"),
        ("cyclists", "Q2309784", "P106", 15, "spt-cyclist", "Name a professional cyclist", "sports"),
        ("cricketers", "Q12299841", "P106", 12, "spt-cricketer", "Name a cricketer", "sports"),
        ("philosophers", "Q4964182", "P106", 20, "gen-philosopher", "Name a philosopher", "general"),
        ("architects", "Q42973", "P106", 16, "gen-architect", "Name a famous architect", "general"),
        ("inventors", "Q205375", "P106", 15, "gen-inventor", "Name an inventor", "general"),
        ("explorers", "Q11900058", "P106", 12, "gen-explorer", "Name a famous explorer", "general"),
        ("monarchs", "Q116", "P39", 22, "gen-monarch", "Name a monarch, king, or queen", "general"),
        ("companies", "Q4830453", "P31", 28, "gen-company", "Name a well-known company or corporation", "general"),
        ("websites", "Q35127", "P31", 16, "gen-website", "Name a website or online platform", "general"),
        ("spacecraft", "Q40218", "P31", 12, "gen-spacecraft", "Name a spacecraft or space probe", "general"),
        ("stars", "Q523", "P31", 12, "gen-star", "Name a star in the night sky", "general"),
        ("compounds", "Q11173", "P31", 28, "gen-compound", "Name a chemical compound or molecule", "general"),
        ("diseases", "Q12136", "P31", 20, "gen-disease", "Name a medical disease or condition", "general"),
        ("cat_breeds", "Q43577", "P31", 2, "gen-cat-breed", "Name a cat breed", "general"),
        ("horse_breeds", "Q23002039", "P31", 2, "gen-horse-breed", "Name a horse breed", "general"),
        ("breads", "Q7802", "P31", 2, "gen-bread", "Name a type of bread", "general"),
        ("soups", "Q41415", "P31", 2, "gen-soup", "Name a soup or stew", "general"),
        ("sauces", "Q178359", "P31", 2, "gen-sauce", "Name a sauce or condiment", "general"),
        ("pastries", "Q477248", "P31", 2, "gen-pastry", "Name a pastry or baked sweet", "general"),
        ("wine_grapes", "Q10978", "P31", 3, "gen-grape", "Name a wine grape variety", "general"),
        ("comics_chars", "Q1114461", "P31", 8, "gen-comic-char", "Name a comic book character", "general"),
        ("skyscrapers", "Q11303", "P31", 8, "geo-skyscraper", "Name a skyscraper or tall tower", "geography"),
        ("glaciers", "Q35666", "P31", 4, "geo-glacier", "Name a glacier", "geography"),
        ("caves", "Q35509", "P31", 5, "geo-cave", "Name a cave or cavern", "geography"),
        ("canyons", "Q150784", "P31", 3, "geo-canyon", "Name a canyon or gorge", "geography"),
        ("bays", "Q39594", "P31", 6, "geo-bay", "Name a bay or gulf", "geography"),
        ("capes", "Q185113", "P31", 5, "geo-cape", "Name a cape or headland", "geography"),
        ("nobel_laureates", "Q7191", "P166", 20, "gen-nobel", "Name a Nobel Prize laureate", "general"),
    ]

    for key, qid, prop, min_sl, pid, ptext, cat in master_lists:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:{prop} wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 2600"""
        rows = run_sparql_rows(key, q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(pid, ptext, cat, build_balanced_tiers(items, MAX_SEED_ANSWERS))
        add_letter_slices(rows, pid, f"{ptext} starting with the letter {{L}}", cat)

    # Footballers fast query (sitelinks >= 48)
    fb_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P106 wd:Q937857 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 48)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2400"""
    fb_rows = run_sparql_rows("footballers_v2", fb_q)
    fb_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in fb_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("spt-footballer", "Name a professional footballer (soccer player)", "sports", build_balanced_tiers(fb_items, MAX_SEED_ANSWERS))
    add_letter_slices(fb_rows, "spt-footballer", "Name a footballer starting with the letter {L}", "sports")

    # Vertebrate & animal common names via P1843 (higher sitelink floor so SPARQL stays fast)
    animal_classes = [
        ("mammals_en", "Q7377", "gen-mammal", "Name a mammal species", "general"),
        ("birds_en", "Q5113", "gen-bird", "Name a bird species", "general"),
        ("reptiles_en", "Q10811", "gen-reptile", "Name a reptile species", "general"),
        ("fishes_en", "Q152", "gen-fish", "Name a fish species", "general"),
    ]
    for key, qid, pid, ptext, cat in animal_classes:
        q = f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item wdt:P1843 ?common .
  FILTER(LANG(?common) = "en")
  ?item wdt:P105 wd:Q7432 .
  ?item wdt:P171* wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 30)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 900"""
        rows = run_sparql_rows(key, q)
        items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in rows if (c := clean_label(r["itemLabel"]))]
        reg.add(pid, ptext, cat, build_balanced_tiers(items, MAX_SEED_ANSWERS))
        add_letter_slices(rows, pid, f"{ptext} starting with the letter {{L}}", cat)

    # People & places by country
    people_country_queries = [
        ("authors_country", "Q36180", "P106", "P27", 22, "gen-author-nat", "Name an author from {G}", "general"),
        ("bands_country", "Q215380", "P31", "P495", 16, "gen-band-nat", "Name a band from {G}", "general"),
        ("clubs_country", "Q476028", "P31", "P17", 15, "spt-club-nat", "Name a football club in {G}", "sports"),
        ("stadiums_country", "Q483110", "P31", "P17", 8, "spt-stad-nat", "Name a sports stadium in {G}", "sports"),
        ("islands_country", "Q23442", "P31", "P17", 8, "geo-isl-nat", "Name an island in {G}", "geography"),
        ("lakes_country", "Q23397", "P31", "P17", 8, "geo-lak-nat", "Name a lake in {G}", "geography"),
        ("parks_country", "Q46169", "P31", "P17", 4, "geo-prk-nat", "Name a national park in {G}", "geography"),
        ("unesco_country", "Q9259", "P1435", "P17", 5, "geo-her-nat", "Name a World Heritage Site in {G}", "geography"),
        ("dishes_country", "Q746549", "P31", "P495", 3, "gen-dish-nat", "Name a traditional food or dish from {G}", "general"),
        ("universities_country", "Q3918", "P31", "P17", 18, "gen-uni-nat", "Name a university in {G}", "general"),
        ("museums_country", "Q33506", "P31", "P17", 10, "gen-mus-nat", "Name a museum in {G}", "general"),
        ("castles_country", "Q23413", "P31", "P17", 6, "gen-cas-nat", "Name a castle or palace in {G}", "general"),
    ]
    for key, qid, prop, grp_prop, min_sl, id_pref, fmt, cat in people_country_queries:
        q = f"""
SELECT ?itemLabel ?grpLabel ?sitelinks WHERE {{
  ?item wdt:{prop} wd:{qid} .
  ?item wdt:{grp_prop} ?grp .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sl})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sitelinks) LIMIT 3200"""
        rows = run_sparql_rows(key, q)
        add_group_slices(rows, "grpLabel", id_pref, fmt, cat)
        if key == "authors_country":
            author_items = [
                (c[0], float(r.get("sitelinks", 1) or 1), c[1])
                for r in rows
                if (c := clean_label(r["itemLabel"]))
            ]
            reg.add("gen-author", "Name an author or writer", "general", build_balanced_tiers(author_items, MAX_SEED_ANSWERS))
            add_letter_slices(rows, "gen-author", "Name an author or writer starting with the letter {L}", "general")

    return added


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

    print("2. Deepening islands & archipelagos (Bonaire, Aruba, Curacao, territories)...")
    deepen_islands_and_archipelagos(reg)
    print(f"   geo-island: {reg.by_id['geo-island']['answerCount']}, geo-archipelago: {reg.by_id['geo-archipelago']['answerCount']}")

    print("3. Fetching & slicing master Wikidata datasets (TV, anime, manga, songs, movies, cities, science, sports)...")
    n_wd = enrich_from_master_wikidata(reg)
    print(f"   Added {n_wd} Wikidata faceted prompts (total: {len(reg.prompts)}).")

    print("4. Slicing large core prompts by starting letter (after island/movie deepening)...")
    n_sliced = slice_existing_prompts(reg)
    print(f"   Added {n_sliced} letter-slice prompts (total: {len(reg.prompts)}).")

    print("5. Generating dictionary wordcraft prompts...")
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

    for cid, payload in enumerate(chunks):
        chunk_path = OUT_CHUNKS_DIR / f"chunk-{cid:03d}.json"
        chunk_path.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )

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
    print(f"Total answers: {total_answers:,}")


if __name__ == "__main__":
    main()
