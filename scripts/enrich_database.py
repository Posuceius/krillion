#!/usr/bin/env python3
"""
Enrich Krillion's 159 curated seed prompts using:
  1. Wikidata SPARQL (entity labels + Wikipedia sitelink counts as familiarity)
  2. Local English dictionaries (/usr/share/dict/american-english, british-english)
     paired with Peter Norvig's English word-frequency corpus (count_1w.txt).

Outputs:
  - public/data/prompts/<id>.json   (compact per-prompt tier files)
  - src/data/manifest.ts            (lightweight prompt metadata + packs + totals)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
SPARQL_CACHE = CACHE_DIR / "sparql"
WORD_FREQ_PATH = CACHE_DIR / "word_freq.txt"
OUT_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

TIERS = ["plankton", "tooclever", "schooler", "rare", "deepcut", "krillion"]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "KrillionStaticBuilder/1.0 (https://gitlab.com; static-pages-game)"


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


def clean_wikidata_label(label: str) -> tuple[str, list[str]] | None:
    label = label.strip()
    if not label:
        return None
    if re.match(r"^Q\d+$", label):
        return None
    if any(bad in label for bad in ["\n", "[", "]", "{", "}", "http://", "https://"]):
        return None
    lower = label.lower()
    if lower.startswith(("list of ", "category:", "template:", "wikipedia:")):
        return None
    if len(label) > 52:
        return None

    # Require at least some ASCII letters
    if not re.search(r"[a-zA-Z]", label):
        return None

    aliases: list[str] = []
    # Strip trailing Wikipedia disambiguation e.g. "Mercury (planet)"
    m = re.match(r"^(.+?)\s*\([^)]{2,30}\)$", label)
    if m:
        short = m.group(1).strip()
        if len(short) >= 2:
            aliases.append(label)
            label = short

    return label, aliases


def run_sparql(query: str, min_delay: float = 0.7) -> list[tuple[str, int]]:
    SPARQL_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(query.encode("utf-8")).hexdigest()[:20]
    cache_file = SPARQL_CACHE / f"{key}.json"

    if cache_file.exists():
        data = json.loads(cache_file.read_text("utf-8"))
        return [(row["label"], row["sitelinks"]) for row in data]

    url = f"{SPARQL_ENDPOINT}?{urllib.parse.urlencode({'query': query})}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": USER_AGENT,
        },
    )

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            time.sleep(0.55 * (attempt + 1))
            with urllib.request.urlopen(req, timeout=14) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rows: list[dict[str, Any]] = []
            for b in payload.get("results", {}).get("bindings", []):
                lbl_obj = b.get("itemLabel") or b.get("label")
                if not lbl_obj:
                    continue
                # Skip non-English fallback if it is literally QID
                val = lbl_obj.get("value", "")
                if re.match(r"^Q\d+$", val):
                    continue
                sl = int(b.get("sitelinks", {}).get("value", 1))
                rows.append({"label": val, "sitelinks": sl})
            cache_file.write_text(json.dumps(rows), encoding="utf-8")
            return [(r["label"], r["sitelinks"]) for r in rows]
        except Exception as exc:
            last_err = exc
            time.sleep(2.0 * (attempt + 1))

    print(f"  [WARN] SPARQL query failed ({last_err})")
    return []


def wd_instance(qid: str, limit: int = 2000, min_sitelinks: int = 1, subclass: bool = False) -> str:
    prop = "wdt:P31/wdt:P279*" if subclass else "wdt:P31"
    return f"""
SELECT ?itemLabel ?sitelinks WHERE {{
  ?item {prop} wd:{qid} .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY DESC(?sitelinks)
LIMIT {limit}
""".strip()


# Map prompt ID -> SPARQL query
SPARQL_QUERIES: dict[str, str] = {
    # GENERAL
    "gen-magazine": wd_instance("Q41298", 2200, 3),
    "gen-browser": wd_instance("Q6368", 800, 1),
    "gen-instrument": wd_instance("Q110295396", 2000, 2, subclass=True),
    "gen-element": wd_instance("Q11344", 300, 1),
    "gen-dog-breed": wd_instance("Q39367", 1500, 1),
    "gen-pasta": wd_instance("Q178", 600, 1, subclass=True),
    "gen-board-game": wd_instance("Q131436", 2200, 2),
    "gen-cheese": wd_instance("Q10943", 1500, 1, subclass=True),
    "gen-programming-lang": wd_instance("Q9143", 1500, 2),
    "gen-spice-herb": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q42527 } UNION { ?item wdt:P31 wd:Q207123 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 1)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "gen-constellation": wd_instance("Q8928", 300, 1),
    "gen-dinosaur": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P105 wd:Q34740 .
  ?item wdt:P171* wd:Q430 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "gen-cocktail": wd_instance("Q134768", 1200, 1),
    "gen-gemstone": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q83437 } UNION { ?item wdt:P31 wd:Q7946 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "gen-greek-god": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q22989102 } UNION { ?item wdt:P31 wd:Q11688446 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 1)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "gen-car-brand": wd_instance("Q786820", 1500, 2),
    "gen-coffee": wd_instance("Q20932605", 600, 1, subclass=True),
    "gen-composer": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P106 wd:Q36834 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 15)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "gen-bird-prey": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P105 wd:Q7432 .
  { ?item wdt:P171* wd:Q25372 } UNION { ?item wdt:P171* wd:Q25352 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "gen-moon": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31/wdt:P279* wd:Q2537 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "gen-painting": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q3305213 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 6)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "gen-music-genre": wd_instance("Q188451", 2200, 3),
    "gen-dessert": wd_instance("Q182940", 1800, 2, subclass=True),
    "gen-tree": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q10884 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "gen-bone": wd_instance("Q265868", 800, 2),
    "gen-superhero": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q188784 } UNION { ?item wdt:P106 wd:Q188784 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "gen-appliance": wd_instance("Q212920", 800, 1, subclass=True),
    "gen-currency": wd_instance("Q8142", 1200, 2),
    "gen-cloud": wd_instance("Q8074", 400, 1, subclass=True),
    "gen-venomous": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P171 wd:Q2102 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "gen-tea": wd_instance("Q6097", 600, 1),
    "gen-console": wd_instance("Q8076", 800, 1),
    "gen-phobia": wd_instance("Q175854", 800, 1),
    "gen-volcano": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q8072 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 6)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "gen-flower": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q506 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "gen-hat": wd_instance("Q80151", 800, 1),
    "gen-fabric": wd_instance("Q28823", 1000, 1),
    "gen-sea-creature": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P171 wd:Q152 } UNION { ?item wdt:P171 wd:Q12796 } UNION { ?item wdt:P31 wd:Q16521 . ?item wdt:P171 wd:Q160 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "gen-scientist": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P106 wd:Q901 } UNION { ?item wdt:P106 wd:Q169470 } UNION { ?item wdt:P106 wd:Q593644 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 25)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "gen-breakfast": wd_instance("Q80973", 600, 1, subclass=True),
    "gen-martial-art": wd_instance("Q11417", 1000, 1),
    "gen-dance": wd_instance("Q11639", 1500, 2, subclass=True),
    "gen-nut-seed": wd_instance("Q11009", 600, 1, subclass=True),
    "gen-tool": wd_instance("Q2578402", 1000, 1, subclass=True),
    "gen-mythical": wd_instance("Q2239243", 1500, 2),
    "gen-card-game": wd_instance("Q142714", 1200, 1),
    "gen-unit": wd_instance("Q47574", 1200, 2),
    "gen-bridge": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q12280 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 6)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "gen-color-shade": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P279* wd:Q1088 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 1)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 600""",
    "gen-knot": wd_instance("Q171076", 600, 1, subclass=True),
    "gen-tree-nut-fruit": wd_instance("Q3314483", 1000, 3),
    "gen-mushroom": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q83093 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 2)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "gen-sandwich": wd_instance("Q28803", 800, 1),
    "gen-boat": wd_instance("Q2235308", 1200, 2),

    # WORDS (Wikidata foods/colors complement dictionary)
    "wrd-color-word": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P279* wd:Q11427 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 1)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 400""",

    # MOVIES
    "mov-best-picture": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P166 wd:Q102427 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 400""",
    "mov-pixar": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P272 wd:Q127552 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "mov-ghibli": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P272 wd:Q182950 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "mov-hitchcock": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P57 wd:Q7374 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "mov-scifi-classic": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q471839 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "mov-horror": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q200092 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "mov-disney-anim": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P272 wd:Q1047410 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 400""",
    "mov-musical": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q842256 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 6)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1600""",
    "mov-spy": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q2297927 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 5)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "mov-heist": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q496523 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "mov-western": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q172980 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 5)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "mov-director": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P106 wd:Q2526255 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 32)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "mov-film-composer": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P106 wd:Q1415090 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "mov-sports": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q1339864 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "mov-christmas": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P136 wd:Q28026639 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1000""",
    "mov-silent": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q226730 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 5)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1600""",
    "mov-tarantino": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P57 wd:Q3772 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 100""",
    "mov-time-travel": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q11424 .
  ?item wdt:P921 wd:Q182154 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 800""",

    # SPORTS
    "spt-olympic-sport": wd_instance("Q212434", 500, 1),
    "spt-f1-circuit": wd_instance("Q1777138", 500, 1),
    "spt-chess": wd_instance("Q103632", 1200, 1, subclass=True),
    "spt-stadium": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q483110 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "spt-olympian": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P166 wd:Q15243387 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 12)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "spt-grand-slam-tennis": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P106 wd:Q10833314 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 18)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "spt-premier-league": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P118 wd:Q9448 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 300""",
    "spt-cycling": wd_instance("Q15091377", 1500, 2),
    "spt-winter-olympic": wd_instance("Q216613", 300, 1),
    "spt-martial-gear": wd_instance("Q1212767", 1000, 1, subclass=True),

    # GEOGRAPHY
    "geo-europe-capital": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?country wdt:P31 wd:Q3624078 .
  ?country wdt:P30 wd:Q46 .
  ?country wdt:P36 ?item .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "geo-us-state-capital": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?state wdt:P31 wd:Q35657 .
  ?state wdt:P36 ?item .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 100""",
    "geo-south-america-city": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 ?c .
  ?c wdt:P30 wd:Q18 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1800""",
    "geo-australia-city": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 wd:Q408 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "geo-canada-city": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q515 .
  ?item wdt:P17 wd:Q16 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 6)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1200""",
    "geo-asian-country": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q3624078 .
  ?item wdt:P30 wd:Q48 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "geo-african-country": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q3624078 .
  ?item wdt:P30 wd:Q15 .
  ?item wikibase:sitelinks ?sitelinks .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 200""",
    "geo-river": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q4022 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2400""",
    "geo-mountain-range": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q46831 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 5)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "geo-island": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q23442 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 12)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2400""",
    "geo-desert": wd_instance("Q8514", 1000, 1),
    "geo-sea-ocean": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q165 } UNION { ?item wdt:P31 wd:Q9430 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 3)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 800""",
    "geo-landmark": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P1435 wd:Q9259 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2000""",
    "geo-national-park": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q46169 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 5)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "geo-strait-canal": """
SELECT ?itemLabel ?sitelinks WHERE {
  { ?item wdt:P31 wd:Q37901 } UNION { ?item wdt:P31 wd:Q12284 } .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 4)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 1500""",
    "geo-lake": """
SELECT ?itemLabel ?sitelinks WHERE {
  ?item wdt:P31 wd:Q23397 .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 10)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 2200""",
    "geo-peninsula": wd_instance("Q34763", 1200, 3),
    "geo-archipelago": wd_instance("Q33837", 1200, 3),
    "geo-waterfall": wd_instance("Q34038", 1200, 2),
}


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


def load_english_dictionary() -> set[str]:
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
                if not w or "'" in w or not w.isalpha():
                    continue
                if w.islower() and len(w) >= 2:
                    words.add(w)
    return words


def has_double_letter(word: str) -> bool:
    return any(word[i] == word[i + 1] for i in range(len(word) - 1))


def double_pair_count(word: str) -> int:
    count = 0
    i = 0
    while i < len(word) - 1:
        if word[i] == word[i + 1]:
            count += 1
            i += 2
        else:
            i += 1
    return count


def dictionary_candidates(
    prompt_id: str, dict_words: set[str], freqs: dict[str, int]
) -> list[tuple[str, float]]:
    """Return (word, score) candidates for dictionary-driven word prompts."""
    matched: list[str] = []

    if prompt_id == "wrd-starts-q":
        matched = [w for w in dict_words if w.startswith("q") and len(w) >= 3]
    elif prompt_id == "wrd-starts-z":
        matched = [w for w in dict_words if w.startswith("z") and len(w) >= 3]
    elif prompt_id == "wrd-starts-x":
        matched = [w for w in dict_words if w.startswith("x") and len(w) >= 3]
    elif prompt_id == "wrd-ending-ology":
        matched = [w for w in dict_words if w.endswith("ology") and len(w) >= 6]
    elif prompt_id == "wrd-palindrome":
        matched = [w for w in dict_words if len(w) >= 3 and w == w[::-1]]
    elif prompt_id == "wrd-no-vowels":
        vowels = set("aeiou")
        matched = [w for w in dict_words if len(w) >= 2 and not (set(w) & vowels)]
    elif prompt_id == "wrd-double-consonant":
        matched = [w for w in dict_words if double_pair_count(w) >= 2 and len(w) >= 6]
    elif prompt_id == "wrd-longest-common":
        matched = [w for w in dict_words if len(w) >= 14]
    elif prompt_id == "wrd-double-food":
        # Intersect Wikidata food items with double-letter single words
        food_rows = run_sparql(wd_instance("Q2095", 2400, 2, subclass=False))
        out: list[tuple[str, float]] = []
        for lbl, sl in food_rows:
            cleaned = clean_wikidata_label(lbl)
            if not cleaned:
                continue
            word = cleaned[0]
            if " " not in word and word.isalpha() and has_double_letter(word.lower()):
                out.append((word.title(), float(sl)))
        return out
    else:
        return []

    scored: list[tuple[str, float]] = []
    for w in matched:
        f = freqs.get(w, 0)
        # Rank by log frequency; rare dict-only words get small length-based tiebreak
        score = math.log10(f + 1) if f > 0 else max(0.1, 1.0 / max(1, len(w)))
        scored.append((w.capitalize(), score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:2600]


def assign_wikidata_tier(sitelinks: int, rank_ratio: float) -> str:
    """Calibrate tier from both absolute Wikipedia sitelink count and relative rank."""
    if sitelinks >= 65 and rank_ratio <= 0.05:
        return "plankton"
    if sitelinks >= 32 and rank_ratio <= 0.14:
        return "tooclever"
    if sitelinks >= 16 and rank_ratio <= 0.30:
        return "schooler"
    if sitelinks >= 7 and rank_ratio <= 0.56:
        return "rare"
    if sitelinks >= 3 and rank_ratio <= 0.82:
        return "deepcut"
    return "krillion"


def assign_word_tier(score: float, rank_ratio: float) -> str:
    if score >= 6.8 and rank_ratio <= 0.05:
        return "plankton"
    if score >= 5.8 and rank_ratio <= 0.14:
        return "tooclever"
    if score >= 4.9 and rank_ratio <= 0.32:
        return "schooler"
    if score >= 3.9 and rank_ratio <= 0.58:
        return "rare"
    if score >= 2.2 and rank_ratio <= 0.84:
        return "deepcut"
    return "krillion"


def merge_prompt(
    seed: dict[str, Any],
    candidates: list[tuple[str, float, list[str]]],
    is_word_prompt: bool,
) -> dict[str, list[Any]]:
    tiers: dict[str, list[Any]] = {t: [] for t in TIERS}
    seen_norms: dict[str, str] = {}

    def register(canonical: str, tier: str, aliases: list[str] | None = None) -> bool:
        forms = [canonical, *(aliases or [])]
        variants_to_add: list[str] = []
        valid_aliases: list[str] = []

        canon_norm = normalize_answer(canonical)
        if not canon_norm:
            return False
        for v in plural_variants(canon_norm):
            prev = seen_norms.get(v)
            if prev is not None:
                return False
            variants_to_add.append(v)

        for al in aliases or []:
            al_norm = normalize_answer(al)
            if not al_norm:
                continue
            al_vars = plural_variants(al_norm)
            if any(seen_norms.get(v) not in (None, tier) for v in al_vars):
                continue
            valid_aliases.append(al)
            for v in al_vars:
                if v not in variants_to_add:
                    variants_to_add.append(v)

        for v in variants_to_add:
            seen_norms[v] = tier

        if valid_aliases:
            tiers[tier].append([canonical, *valid_aliases])
        else:
            tiers[tier].append(canonical)
        return True

    # 1. Always preserve curated seed answers first at their exact tiers
    for ans in seed["answers"]:
        register(ans["canonical"], ans["tier"], ans.get("aliases"))

    # 2. Add enriched candidates sorted descending by popularity score
    candidates_sorted = sorted(candidates, key=lambda x: x[1], reverse=True)
    total = max(1, len(candidates_sorted))
    for idx, (label, score, aliases) in enumerate(candidates_sorted):
        ratio = idx / total
        tier = (
            assign_word_tier(score, ratio)
            if is_word_prompt
            else assign_wikidata_tier(int(score), ratio)
        )
        register(label, tier, aliases)

    return tiers


def main() -> None:
    seeds: list[dict[str, Any]] = json.loads(SEED_PATH.read_text("utf-8"))
    freqs = load_word_frequencies()
    dict_words = load_english_dictionary()
    print(f"Loaded {len(seeds)} seed prompts, {len(dict_words):,} dict words, {len(freqs):,} freq entries.")

    OUT_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any stale JSON files
    for old_file in OUT_PROMPTS_DIR.glob("*.json"):
        old_file.unlink()

    manifest_entries: list[dict[str, Any]] = []
    total_answers = 0
    largest: list[tuple[int, str]] = []

    for i, seed in enumerate(seeds, 1):
        pid = seed["id"]
        candidates: list[tuple[str, float, list[str]]] = []
        is_word_prompt = False

        if pid in {
            "wrd-starts-q",
            "wrd-starts-z",
            "wrd-starts-x",
            "wrd-ending-ology",
            "wrd-palindrome",
            "wrd-no-vowels",
            "wrd-double-consonant",
            "wrd-longest-common",
            "wrd-double-food",
        }:
            is_word_prompt = pid != "wrd-double-food"
            for word, sc in dictionary_candidates(pid, dict_words, freqs):
                candidates.append((word, sc, []))

        if pid in SPARQL_QUERIES:
            raw_rows = run_sparql(SPARQL_QUERIES[pid])
            for lbl, sl in raw_rows:
                cleaned = clean_wikidata_label(lbl)
                if cleaned:
                    c_label, c_aliases = cleaned
                    candidates.append((c_label, float(sl), c_aliases))

        tiers_map = merge_prompt(seed, candidates, is_word_prompt)
        count = sum(len(v) for v in tiers_map.values())
        total_answers += count
        largest.append((count, pid))

        out_obj = {"id": pid, "tiers": tiers_map}
        (OUT_PROMPTS_DIR / f"{pid}.json").write_text(
            json.dumps(out_obj, separators=(",", ":")), encoding="utf-8"
        )

        manifest_entries.append(
            {
                "id": pid,
                "text": seed["text"],
                "category": seed["category"],
                "answerCount": count,
            }
        )

        if i % 5 == 0 or count >= 400:
            print(f"[{i}/{len(seeds)}] {pid}: {count} answers (running total: {total_answers:,})")

    # Build THEMED_PACKS preserving exact 5-chapter grouping per category
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

    themed_packs = []
    for cat_id, title, subtitle, unit_label, accent, ch_titles in packs_meta:
        cat_ids = [m["id"] for m in manifest_entries if m["category"] == cat_id]
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

    manifest_ts = (
        "// Auto-generated by scripts/enrich_database.py\n"
        "import type { PromptMeta, ThemedPack } from '../domain/types';\n\n"
        f"export const TOTAL_ANSWER_COUNT = {total_answers};\n\n"
        f"export const PROMPT_MANIFEST: PromptMeta[] = {json.dumps(manifest_entries, indent=2)};\n\n"
        f"export const THEMED_PACKS: ThemedPack[] = {json.dumps(themed_packs, indent=2)};\n"
    )
    OUT_MANIFEST_PATH.write_text(manifest_ts, encoding="utf-8")

    largest.sort(reverse=True)
    print("\n=== ENRICHMENT COMPLETE ===")
    print(f"Prompts: {len(manifest_entries)}")
    print(f"Total answers: {total_answers:,}")
    print("Top 10 largest prompts:")
    for cnt, pid in largest[:10]:
        print(f"  {pid}: {cnt:,}")


if __name__ == "__main__":
    main()
