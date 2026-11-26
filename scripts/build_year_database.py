#!/usr/bin/env python3
"""
Build a 2,600+ prompt Krillion database (365+ consecutive non-repeating days)
from:
  1. All 159 existing curated + Wikidata-enriched prompts (public/data/prompts & seed_prompts.json)
  2. Letter-slices of large existing enriched prompts
  3. Fast cached master Wikidata SPARQL datasets sliced by country/state/year/decade/genre/letter
  4. Rich English wordcraft prompts derived from /usr/share/dict/ + Norvig 333k word frequencies

Outputs:
  - public/data/chunks/chunk-00.json .. chunk-63.json (64 deterministic chunks)
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
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
MASTER_CACHE = CACHE_DIR / "master"
WORD_FREQ_PATH = CACHE_DIR / "word_freq.txt"
OLD_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
ENRICHED_159_DIR = CACHE_DIR / "enriched_159"
OUT_CHUNKS_DIR = ROOT / "public" / "data" / "chunks"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

NUM_CHUNKS = 64
TIERS = ["plankton", "tooclever", "schooler", "rare", "deepcut", "krillion"]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "KrillionStaticBuilder/1.1 (https://gitlab.com; static-pages-game)"
MIN_ANSWERS = 30
MAX_FACET_ANSWERS = 450
MAX_SEED_ANSWERS = 1800


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
        return json.loads(cache_file.read_text("utf-8"))

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
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rows: list[dict[str, str]] = []
            for b in payload.get("results", {}).get("bindings", []):
                row = {k: v.get("value", "") for k, v in b.items()}
                lbl = row.get("itemLabel", "")
                if not lbl or re.match(r"^Q\d+$", lbl):
                    continue
                rows.append(row)
            cache_file.write_text(json.dumps(rows), encoding="utf-8")
            print(f"  [SPARQL] {name}: {len(rows)} rows")
            return rows
        except Exception as exc:
            print(f"  [SPARQL retry {attempt+1}] {name}: {exc}")
            time.sleep(1.5 * (attempt + 1))

    cache_file.write_text("[]", encoding="utf-8")
    return []


def build_balanced_tiers(
    scored_items: list[tuple[str, float, list[str]]],
    max_answers: int = MAX_FACET_ANSWERS,
) -> dict[str, list[Any]] | None:
    """Deduplicate items, rank descending by score, and split into all 6 non-empty tiers."""
    # Sort descending by score
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

    # Quantile boundaries guaranteeing every tier gets >= 2 items
    # Distribution: 6% plankton, 10% tooclever, 16% schooler, 24% rare, 26% deepcut, 18% krillion
    cuts = [
        max(2, round(n * 0.06)),
        max(4, round(n * 0.16)),
        max(7, round(n * 0.32)),
        max(12, round(n * 0.56)),
        max(18, round(n * 0.82)),
        n,
    ]
    # Ensure strictly increasing cuts within n
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
            # Trim only if massive while preserving all tiers
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


def slice_existing_prompts(reg: PromptRegistry) -> int:
    """Slice large existing enriched prompts by starting letter."""
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

    # 1. Cities by continent & country
    continents = [
        ("eu", "Q46", "European", 10),
        ("as", "Q48", "Asian", 10),
        ("af", "Q15", "African", 6),
        ("na", "Q49", "North American", 18),
        ("sa", "Q18", "South American", 10),
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

    # Also U.S. cities by state
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

    # 2. Films by decade, year, genre, country, letter (using indexed xsd:dateTime range!)
    film_decades = [
        ("1940s", 1940, 1949, 10),
        ("1950s", 1950, 1959, 12),
        ("1960s", 1960, 1969, 14),
        ("1970s", 1970, 1979, 14),
        ("1980s", 1980, 1989, 16),
        ("1990s", 1990, 1999, 18),
        ("2000s", 2000, 2009, 20),
        ("2010s", 2010, 2019, 20),
        ("2020s", 2020, 2025, 16),
    ]
    all_films: list[dict[str, str]] = []
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
        # Decade prompt
        dec_items = []
        for r in rows:
            c = clean_label(r["itemLabel"])
            if c:
                dec_items.append((c[0], float(r.get("sitelinks", 1) or 1), c[1]))
        reg.add(f"mov-decade-{dlabel}", f"Name a movie from the {dlabel}", "movies", build_balanced_tiers(dec_items))
        add_group_slices(rows, "year", "mov-year", "Name a movie released in {G}", "movies", min_group=35)
        add_letter_slices(rows, f"mov-{dlabel}", f"Name a {dlabel} movie starting with the letter {{L}}", "movies")

    add_letter_slices(all_films, "mov-all", "Name a movie starting with the letter {L}", "movies")
    one_word_films = [
        r for r in all_films
        if (c := clean_label(r["itemLabel"])) and " " not in c[0] and "-" not in c[0]
    ]
    add_letter_slices(one_word_films, "mov-oneword", "Name a one-word movie starting with the letter {L}", "movies")

    # Film genres
    film_genres = [
        ("action", "Q188473", "Action"),
        ("adventure", "Q319221", "Adventure"),
        ("animated", "Q202866", "Animated"),
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
        for r in rows:
            c = clean_label(r["itemLabel"])
            if c:
                items.append((c[0], float(r.get("sitelinks", 1) or 1), c[1]))
        reg.add(f"mov-genre-{gid}", f"Name a {gname} movie", "movies", build_balanced_tiers(items))
        add_letter_slices(rows, f"mov-genre-{gid}", f"Name a {gname} movie starting with the letter {{L}}", "movies")

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

    # 3. TV Series & Video Games (lean non-OPTIONAL queries for fast execution)
    tv_q = """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q5398419 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 16)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2800"""
    tv_rows = run_sparql_rows("tv_series", tv_q)
    tv_items = [(c[0], float(r.get("sitelinks", 1) or 1), c[1]) for r in tv_rows if (c := clean_label(r["itemLabel"]))]
    reg.add("gen-tv-show", "Name a TV show or series", "general", build_balanced_tiers(tv_items, MAX_SEED_ANSWERS))
    add_letter_slices(tv_rows, "gen-tv", "Name a TV show starting with the letter {L}", "general")

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

    # 4. Books/Novels, Authors, Bands, Singers, Albums, Actors, Painters
    master_lists = [
        ("books", "Q7725634", "P31", 15, "gen-book", "Name a famous book or novel", "general"),
        ("authors", "Q36180", "P106", 28, "gen-author", "Name an author or writer", "general"),
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
        ("mammals", "Q7377", "P171", 4, "gen-mammal", "Name a mammal species or genus", "general"),
        ("birds", "Q5113", "P171", 4, "gen-bird", "Name a bird species", "general"),
        ("fishes", "Q152", "P171", 3, "gen-fish", "Name a fish species", "general"),
        ("snakes", "Q2102", "P171", 2, "gen-snake", "Name a snake species", "general"),
        ("dishes", "Q746549", "P31", 6, "gen-dish", "Name a traditional dish or food", "general"),
        ("football_clubs", "Q476028", "P31", 20, "spt-football-club", "Name a football (soccer) club", "sports"),
        ("footballers", "Q937857", "P106", 35, "spt-footballer", "Name a professional footballer (soccer player)", "sports"),
        ("nba_players", "Q3665646", "P106", 20, "spt-nba-player", "Name a basketball player", "sports"),
        ("baseball_players", "Q10871364", "P106", 22, "spt-mlb-player", "Name a baseball player", "sports"),
        ("f1_drivers", "Q10841764", "P106", 12, "spt-f1-driver", "Name a Formula 1 driver", "sports"),
        ("boxers", "Q11338576", "P106", 15, "spt-boxer", "Name a boxer", "sports"),
        ("golfers", "Q13156709", "P106", 14, "spt-golfer", "Name a professional golfer", "sports"),
        ("chess_players", "Q10873124", "P106", 12, "spt-chess-player", "Name a chess grandmaster or player", "sports"),
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

    # People by country for Authors, Scientists, Footballers, Painters, Bands
    people_country_queries = [
        ("authors_country", "Q36180", "P106", "P27", 22, "gen-author-nat", "Name an author from {G}", "general"),
        ("bands_country", "Q215380", "P31", "P495", 16, "gen-band-nat", "Name a band from {G}", "general"),
        ("clubs_country", "Q476028", "P31", "P17", 15, "spt-club-nat", "Name a football club in {G}", "sports"),
        ("stadiums_country", "Q483110", "P31", "P17", 8, "spt-stad-nat", "Name a sports stadium in {G}", "sports"),
        ("rivers_country", "Q4022", "P31", "P17", 8, "geo-riv-nat", "Name a river in {G}", "geography"),
        ("islands_country", "Q23442", "P31", "P17", 8, "geo-isl-nat", "Name an island in {G}", "geography"),
        ("lakes_country", "Q23397", "P31", "P17", 8, "geo-lak-nat", "Name a lake in {G}", "geography"),
        ("parks_country", "Q46169", "P31", "P17", 4, "geo-prk-nat", "Name a national park in {G}", "geography"),
        ("unesco_country", "Q9259", "P1435", "P17", 5, "geo-her-nat", "Name a World Heritage Site in {G}", "geography"),
        ("dishes_country", "Q746549", "P31", "P495", 3, "gen-dish-nat", "Name a traditional food or dish from {G}", "general"),
        ("universities_country", "Q3918", "P31", "P17", 18, "gen-uni-nat", "Name a university in {G}", "general"),
        ("museums_country", "Q33506", "P31", "P17", 10, "gen-mus-nat", "Name a museum in {G}", "general"),
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

    # 1. Exact length (4..10) + starting letter (A..Z), and length (4..9) + ending letter
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
        if 4 <= L <= 10:
            by_len_start[(L, s0)].append((w, sc))
        if 4 <= L <= 9:
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
        emit(
            f"wrd-len{L}-{ltr}",
            f"Name a {L}-letter English word starting with {ltr.upper()}",
            items,
        )

    for (L, ltr), items in sorted(by_len_end.items()):
        if len(items) >= 60:
            emit(
                f"wrd-len{L}-end-{ltr}",
                f"Name a {L}-letter English word ending in {ltr.upper()}",
                items,
            )

    for (s0, s_end), items in sorted(by_start_end.items()):
        if len(items) >= 45:
            emit(
                f"wrd-se-{s0}-{s_end}",
                f"Name an English word starting with {s0.upper()} and ending in {s_end.upper()}",
                items,
            )

    for ch, items in sorted(by_double_char.items()):
        emit(
            f"wrd-dbl-{ch}",
            f"Name an English word containing a double '{ch.upper()}'",
            items,
        )

    for L, items in sorted(by_len_double.items()):
        emit(
            f"wrd-dbl-len{L}",
            f"Name a {L}-letter word containing a double letter",
            items,
        )

    for ltr, items in sorted(by_start_double.items()):
        emit(
            f"wrd-dbl-start-{ltr}",
            f"Name a word starting with {ltr.upper()} that contains a double letter",
            items,
        )

    for (L, rl), items in sorted(by_len_rare_ltr.items()):
        if len(items) >= 42:
            emit(
                f"wrd-has-{rl}-len{L}",
                f"Name a {L}-letter word containing the letter {rl.upper()}",
                items,
            )

    for ch, items in sorted(by_same_start_end.items()):
        emit(
            f"wrd-same-se-{ch}",
            f"Name a word that starts and ends with the letter {ch.upper()}",
            items,
        )

    # 2. Suffixes & Prefixes
    suffixes = [
        "tion", "sion", "ment", "ness", "able", "ible", "less", "ful", "ship",
        "hood", "ism", "ist", "ity", "ous", "ive", "ary", "ory", "ize", "ify",
        "ward", "wise", "like", "gram", "graph", "scope", "phone", "phile",
        "cracy", "mania", "meter", "sphere", "dom", "age", "ure", "ance", "ence",
        "ling", "ette", "ster", "eer", "oid", "ical", "ious", "eous", "esque",
        "proof", "bound", "work", "land", "line", "side", "time", "way", "wood",
        "fish", "bird", "stone", "water", "light", "house", "head", "hand",
        "book", "back", "ball", "craft", "field", "form", "mark", "master",
        "ware", "wright",
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

    # 3. Fun substring & letter-constraint patterns
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

    # 4. Special linguistic & keyboard constraints
    vowels = set("aeiou")
    left_hand = set("qwertasdfgzxcvb")
    right_hand = set("yuiophjklnm")
    top_row = set("qwertyuiop")

    emit(
        "wrd-3-consec-vowels",
        "Name an English word with 3 consecutive vowels (e.g. beauty)",
        [(w, sc) for w, sc in dict_scored if re.search(r"[aeiou]{3}", w)],
    )
    emit(
        "wrd-4-consec-cons",
        "Name an English word with 4 consecutive consonants",
        [(w, sc) for w, sc in dict_scored if re.search(r"[^aeiouy]{4}", w)],
    )
    emit(
        "wrd-no-e-8plus",
        "Name an 8+ letter English word that does not contain the letter E",
        [(w, sc) for w, sc in dict_scored if len(w) >= 8 and "e" not in w],
    )
    emit(
        "wrd-no-ae-7plus",
        "Name a 7+ letter English word with neither A nor E",
        [(w, sc) for w, sc in dict_scored if len(w) >= 7 and "a" not in w and "e" not in w],
    )
    for v in "aeiou":
        emit(
            f"wrd-only-vowel-{v}",
            f"Name a 5+ letter word whose only vowel is {v.upper()} (no other A/E/I/O/U)",
            [(w, sc) for w, sc in dict_scored if len(w) >= 5 and (set(w) & vowels) == {v}],
        )
    emit(
        "wrd-all-5-vowels",
        "Name a word containing all 5 vowels (A, E, I, O, U)",
        [(w, sc) for w, sc in dict_scored if vowels.issubset(set(w))],
    )
    emit(
        "wrd-left-hand",
        "Name a 5+ letter word typed using only the left hand on a QWERTY keyboard",
        [(w, sc) for w, sc in dict_scored if len(w) >= 5 and set(w).issubset(left_hand)],
    )
    emit(
        "wrd-right-hand",
        "Name a 4+ letter word typed using only the right hand on a QWERTY keyboard",
        [(w, sc) for w, sc in dict_scored if len(w) >= 4 and set(w).issubset(right_hand)],
    )
    emit(
        "wrd-top-row",
        "Name a 5+ letter word typed using only the top QWERTY letter row",
        [(w, sc) for w, sc in dict_scored if len(w) >= 5 and set(w).issubset(top_row)],
    )
    emit(
        "wrd-alpha-order",
        "Name a 4+ letter word with all letters in alphabetical order (like 'almost')",
        [(w, sc) for w, sc in dict_scored if len(w) >= 4 and list(w) == sorted(w)],
    )
    emit(
        "wrd-isogram-8",
        "Name an 8+ letter isogram (word with no repeated letters)",
        [(w, sc) for w, sc in dict_scored if len(w) >= 8 and len(set(w)) == len(w)],
    )
    emit(
        "wrd-isogram-9",
        "Name a 9+ letter isogram (word with no repeated letters)",
        [(w, sc) for w, sc in dict_scored if len(w) >= 9 and len(set(w)) == len(w)],
    )
    emit(
        "wrd-isogram-10",
        "Name a 10+ letter isogram (word with no repeated letters)",
        [(w, sc) for w, sc in dict_scored if len(w) >= 10 and len(set(w)) == len(w)],
    )

    return added


def chunk_index_for_id(pid: str) -> int:
    digest = hashlib.sha256(pid.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % NUM_CHUNKS


def main() -> None:
    reg = PromptRegistry()

    print("1. Loading 159 existing curated & enriched prompts...")
    load_seed_and_existing(reg)
    print(f"   Loaded {len(reg.prompts)} prompts.")

    print("2. Slicing large existing prompts by starting letter...")
    n_sliced = slice_existing_prompts(reg)
    print(f"   Added {n_sliced} letter-slice prompts (total: {len(reg.prompts)}).")

    print("3. Fetching & slicing master Wikidata datasets...")
    n_wd = enrich_from_master_wikidata(reg)
    print(f"   Added {n_wd} Wikidata faceted prompts (total: {len(reg.prompts)}).")

    print("4. Generating dictionary wordcraft prompts...")
    dict_scored = load_english_dictionary()
    n_words = generate_wordcraft_prompts(reg, dict_scored)
    print(f"   Added {n_words} wordcraft prompts (total: {len(reg.prompts)}).")

    # Write 64 chunk files cleanly
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
        chunk_path = OUT_CHUNKS_DIR / f"chunk-{cid:02d}.json"
        chunk_path.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )

    # Keep the 4 Themed Packs mapped to their original 25-prompt pack IDs
    packs_meta = [
        (
            "words",
            "WORDS & LANGUAGE",
            "English quirks, loanwords, and lettercraft",
            "chapters",
            "#38bdf8",
            [
                ("Chapter 1: Letter Patterns", "Doubles, palindromes, silent letters & rare starters"),
                ("Chapter 2: Borrowed Tongues", "Loanwords, sheet music & blended portmanteaus"),
                ("Chapter 3: Quirky English", "Collective nouns, sound words, verbs & -ologies"),
                ("Chapter 4: Rhetoric & Ink", "Punctuation, figures of speech, homophones & relics"),
                ("Chapter 5: Lexicon Deep Dive", "Giant words, vowelless gems, NATO & crimsons"),
            ],
        ),
        (
            "movies",
            "AT THE MOVIES",
            "Oscars, animation, cults, directors & scores",
            "pictures",
            "#f05a84",
            [
                ("Reel 1: Classics & Oscars", "Best Picture, Pixar, Ghibli, Hitchcock & solo titles"),
                ("Reel 2: Genre Vault", "Sci-fi, horror, Disney, 90s comedy & musicals"),
                ("Reel 3: Worlds & Tropes", "Monsters, fictional planets, spies, heists & Westerns"),
                ("Reel 4: Auteurs & Themes", "Directors, composers, time travel, space & sports"),
                ("Reel 5: Cinema Lore", "007, Tarantino, holiday films, silents & Pixar pals"),
            ],
        ),
        (
            "sports",
            "SPORTS",
            "Olympians, pro leagues, tactics & arenas",
            "games",
            "#34d399",
            [
                ("Match 1: Global Stage", "Olympics, World Cup, Grand Slams, F1 & golf majors"),
                ("Match 2: Pro Franchises", "NBA, NFL, MLB, NHL & Premier League clubs"),
                ("Match 3: Rules & Craft", "Chess, weight classes, track & field, cricket & pitches"),
                ("Match 4: Ice, Pool & Peak", "Winter Games, swimming, gymnastics, cycling & action"),
                ("Match 5: Legends & Hardware", "Stadiums, rugby, Olympians, trophies & gear"),
            ],
        ),
        (
            "geography",
            "GEOGRAPHY",
            "Capitals, borders, rivers, peaks & islands",
            "expeditions",
            "#fbbf24",
            [
                ("Leg 1: Capitals & Cities", "Europe, US states, South America, Australia & Canada"),
                ("Leg 2: Nations & Borders", "Landlocked, Asia, Africa, microstates & M-nations"),
                ("Leg 3: Water & Landforms", "Rivers, mountain ranges, islands, deserts & seas"),
                ("Leg 4: Wonders & Waters", "Landmarks, national parks, straits, lakes & peninsulas"),
                ("Leg 5: Atlas Oddities", "Flag beasts, Mediterranean, non-Euro, archipelagos & falls"),
            ],
        ),
    ]

    seeds_raw: list[dict[str, Any]] = json.loads(SEED_PATH.read_text("utf-8"))
    themed_packs = []
    for cat_id, title, subtitle, unit_label, accent, ch_titles in packs_meta:
        cat_ids = [s["id"] for s in seeds_raw if s["category"] == cat_id]
        chapters = []
        for idx, (ctitle, csub) in enumerate(ch_titles):
            chapters.append(
                {
                    "id": f"ch-{idx + 1}",
                    "title": ctitle,
                    "subtitle": csub,
                    "promptIds": cat_ids[idx * 5 : idx * 5 + 5],
                }
            )
        themed_packs.append(
            {
                "id": cat_id,
                "title": title,
                "subtitle": subtitle,
                "unitLabel": unit_label,
                "accentColor": accent,
                "chapters": chapters,
            }
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

    from collections import Counter
    cat_counts = Counter(m["category"] for m in manifest_entries)
    print("\n=== FULL-YEAR DATABASE COMPLETE ===")
    print(f"Total prompts: {len(manifest_entries):,} ({year_days} non-repeating daily dives!)")
    print(f"By category: {dict(cat_counts)}")
    print(f"Total answers: {total_answers:,}")


if __name__ == "__main__":
    main()
