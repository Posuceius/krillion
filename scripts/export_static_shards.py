#!/usr/bin/env python3
"""
Export Krillion Zero-Range Hybrid Static JSON Shards + manifest from scripts/.cache/krillion.sqlite3:
  1. Reads prompts, entities, entity_forms, and prompt_answers from krillion.sqlite3.
  2. Strips canonical forms deterministically derivable by the TS client (plural_variants +
     Roman numerals / abbreviations) to keep static JSON shards compact.
  3. Packs normal prompts (answerCount < 20,000) into <= ~320 KiB raw JSON chunks under public/data/chunks/.
  4. Shards mega-prompts (answerCount >= 20,000) into 27 first-letter JSON buckets (a..z + _)
     with multi-bucket routing for cross-letter aliases/subtitles/affixes + summary.json under public/data/mega/.
  5. Removes obsolete public/data/db/ and regenerates src/data/manifest.ts.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "scripts" / "seed_prompts.json"
CACHE_DIR = ROOT / "scripts" / ".cache"
SQLITE_PATH = CACHE_DIR / "krillion.sqlite3"

OLD_DB_DIR = ROOT / "public" / "data" / "db"
OLD_PROMPTS_DIR = ROOT / "public" / "data" / "prompts"
OUT_CHUNKS_DIR = ROOT / "public" / "data" / "chunks"
OUT_MEGA_DIR = ROOT / "public" / "data" / "mega"
OUT_MANIFEST_PATH = ROOT / "src" / "data" / "manifest.ts"

MEGA_THRESHOLD = 20000
TARGET_CHUNK_BYTES = 320 * 1024
SUMMARY_TOP_LIMIT = 3000
SUMMARY_SAMPLE_PER_TIER = 120
ALL_BUCKETS = [chr(c) for c in range(ord("a"), ord("z") + 1)] + ["_"]

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


def client_exact_forms(canonical: str, form_level: int) -> set[str]:
    cnorm = normalize_answer(canonical)
    if not cnorm:
        return set()
    forms = set(plural_variants(cnorm))
    if form_level >= 1:
        r_cnorm = normalize_roman_numerals(cnorm)
        if r_cnorm != cnorm:
            forms.update(plural_variants(r_cnorm))
        a_cnorm = expand_abbreviations(cnorm)
        if a_cnorm != cnorm:
            forms.update(plural_variants(a_cnorm))
    return forms


def bucket_key_for_norm(norm: str) -> str:
    stripped = strip_article(norm) or norm
    if not stripped:
        return "_"
    ch = stripped[0]
    return ch if "a" <= ch <= "z" else "_"


def build_themed_packs() -> list[dict[str, Any]]:
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
    themed_packs: list[dict[str, Any]] = []
    for cat_id, title, subtitle, unit_label, accent, ch_titles in packs_meta:
        cat_ids = [s["id"] for s in seeds_raw if s["category"] == cat_id]
        chapters = [
            {"id": f"ch-{idx + 1}", "title": ctitle, "subtitle": csub, "promptIds": cat_ids[idx * 5 : idx * 5 + 5]}
            for idx, (ctitle, csub) in enumerate(ch_titles)
        ]
        themed_packs.append(
            {"id": cat_id, "title": title, "subtitle": subtitle, "unitLabel": unit_label, "accentColor": accent, "chapters": chapters}
        )
    return themed_packs


def export_from_sqlite(sqlite_path: Path = SQLITE_PATH) -> dict[str, Any]:
    t0 = time.time()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Missing SQLite cache at {sqlite_path}")

    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()

    print("1. Loading entities and normalized forms from SQLite cache...")
    canon_by_eid: dict[int, str] = dict(cur.execute("SELECT id, canonical FROM entities"))
    forms_by_eid: dict[int, list[tuple[str, int]]] = {}
    for norm, eid, fkind in cur.execute("SELECT norm, entity_id, form_kind FROM entity_forms ORDER BY form_kind ASC, norm ASC"):
        forms_by_eid.setdefault(eid, []).append((norm, fkind))

    client_exact_cache: dict[tuple[int, int], set[str]] = {}
    extra_forms_cache: dict[tuple[int, int], list[str]] = {}

    def get_entry_forms(eid: int, fl: int) -> tuple[set[str], list[str]]:
        key = (eid, fl)
        ex = extra_forms_cache.get(key)
        if ex is not None:
            return client_exact_cache[key], ex
        canonical = canon_by_eid[eid]
        c_exact = client_exact_forms(canonical, fl)
        extra: list[str] = []
        for norm, fkind in forms_by_eid.get(eid, ()):
            if fkind <= fl and norm not in c_exact:
                extra.append(norm)
        client_exact_cache[key] = c_exact
        extra_forms_cache[key] = extra
        return c_exact, extra

    prompts_rows = cur.execute(
        "SELECT id, slug, text, category, form_level, pack_only, answer_count FROM prompts ORDER BY id ASC"
    ).fetchall()

    print("2. Preparing output directories (removing obsolete public/data/db/)...")
    for stale_dir in (OLD_DB_DIR, OLD_PROMPTS_DIR, OUT_CHUNKS_DIR, OUT_MEGA_DIR):
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
    OUT_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MEGA_DIR.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    chunk_idx = 0
    current_chunk: dict[str, list[Any]] = {}
    current_chunk_bytes = 2
    chunk_files_count = 0
    mega_files_count = 0
    total_raw_bytes = 0
    max_file_bytes = 0
    daily_eligible = 0
    total_answers = 0

    def flush_chunk() -> None:
        nonlocal chunk_idx, current_chunk, current_chunk_bytes, chunk_files_count, total_raw_bytes, max_file_bytes
        if not current_chunk:
            return
        chunk_name = f"c-{chunk_idx:03d}"
        out_path = OUT_CHUNKS_DIR / f"{chunk_name}.json"
        payload = json.dumps(current_chunk, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        out_path.write_bytes(payload)
        size = len(payload)
        total_raw_bytes += size
        if size > max_file_bytes:
            max_file_bytes = size
        chunk_files_count += 1
        chunk_idx += 1
        current_chunk = {}
        current_chunk_bytes = 2

    print(f"3. Exporting {len(prompts_rows):,} prompts into hybrid zero-Range shards...")
    for pid, slug, text, category, fl, pack_only, answer_count in prompts_rows:
        rows = cur.execute(
            "SELECT entity_id, tier FROM prompt_answers WHERE prompt_id = ? ORDER BY rank ASC",
            (pid,),
        ).fetchall()
        assert len(rows) == answer_count, f"Count mismatch for {slug}: {len(rows)} vs {answer_count}"
        total_answers += answer_count

        meta_entry: dict[str, Any] = {
            "id": slug,
            "text": text,
            "category": category,
            "answerCount": answer_count,
            "formLevel": fl,
        }
        if pack_only:
            meta_entry["packOnly"] = True
        else:
            daily_eligible += 1

        if answer_count >= MEGA_THRESHOLD:
            meta_entry["sharded"] = True
            manifest_entries.append(meta_entry)

            mega_dir = OUT_MEGA_DIR / slug
            mega_dir.mkdir(parents=True, exist_ok=True)
            buckets: dict[str, list[Any]] = {b: [] for b in ALL_BUCKETS}
            tier_counts = [0, 0, 0, 0, 0, 0]
            tier_samples: list[list[str]] = [[] for _ in range(6)]
            top_entries: list[Any] = []

            for rank_idx, (eid, tier_idx) in enumerate(rows):
                canon = canon_by_eid[eid]
                c_exact, extra = get_entry_forms(eid, fl)

                tier_counts[tier_idx] += 1
                if len(tier_samples[tier_idx]) < SUMMARY_SAMPLE_PER_TIER:
                    tier_samples[tier_idx].append(canon)

                if rank_idx < SUMMARY_TOP_LIMIT:
                    if extra:
                        top_entries.append([canon, tier_idx, extra])
                    else:
                        top_entries.append([canon, tier_idx])

                exact_buckets = {bucket_key_for_norm(f) for f in c_exact}
                extra_by_bucket: dict[str, list[str]] = {}
                for f in extra:
                    b = bucket_key_for_norm(f)
                    extra_by_bucket.setdefault(b, []).append(f)

                for b in exact_buckets | set(extra_by_bucket.keys()):
                    b_extra = extra_by_bucket.get(b)
                    if b_extra:
                        buckets[b].append([canon, tier_idx, b_extra])
                    else:
                        buckets[b].append([canon, tier_idx])

            for b in ALL_BUCKETS:
                b_bytes = json.dumps(buckets[b], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                (mega_dir / f"{b}.json").write_bytes(b_bytes)
                size = len(b_bytes)
                total_raw_bytes += size
                if size > max_file_bytes:
                    max_file_bytes = size
                mega_files_count += 1

            summary_obj = {
                "tierCounts": tier_counts,
                "tierSamples": tier_samples,
                "topEntries": top_entries,
            }
            s_bytes = json.dumps(summary_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            (mega_dir / "summary.json").write_bytes(s_bytes)
            size = len(s_bytes)
            total_raw_bytes += size
            if size > max_file_bytes:
                max_file_bytes = size
            mega_files_count += 1
        else:
            entries_list: list[Any] = []
            for eid, tier_idx in rows:
                canon = canon_by_eid[eid]
                _, extra = get_entry_forms(eid, fl)
                if extra:
                    entries_list.append([canon, tier_idx, extra])
                else:
                    entries_list.append([canon, tier_idx])

            entry_json = json.dumps(entries_list, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            est_added = len(slug) + len(entry_json) + 5

            if current_chunk and current_chunk_bytes + est_added > TARGET_CHUNK_BYTES:
                flush_chunk()

            chunk_name = f"c-{chunk_idx:03d}"
            meta_entry["chunk"] = chunk_name
            manifest_entries.append(meta_entry)
            current_chunk[slug] = entries_list
            current_chunk_bytes += est_added

            if current_chunk_bytes >= TARGET_CHUNK_BYTES:
                flush_chunk()

    flush_chunk()
    conn.close()

    print("4. Writing src/data/manifest.ts...")
    themed_packs = build_themed_packs()
    year_days = daily_eligible // 7
    manifest_ts = (
        "// Auto-generated by scripts/export_static_shards.py\n"
        "import type { PromptMeta, ThemedPack } from '../domain/types';\n\n"
        f"export const TOTAL_ANSWER_COUNT = {total_answers};\n\n"
        f"export const YEAR_COVERAGE_DAYS = {year_days};\n\n"
        f"export const PROMPT_MANIFEST: PromptMeta[] = {json.dumps(manifest_entries, separators=(',', ':'))};\n\n"
        f"export const THEMED_PACKS: ThemedPack[] = {json.dumps(themed_packs, indent=2)};\n"
    )
    OUT_MANIFEST_PATH.write_text(manifest_ts, encoding="utf-8")

    stats = {
        "prompts": len(manifest_entries),
        "daily_eligible": daily_eligible,
        "year_days": year_days,
        "total_answers": total_answers,
        "chunk_files": chunk_files_count,
        "mega_files": mega_files_count,
        "total_files": chunk_files_count + mega_files_count,
        "total_raw_mib": total_raw_bytes / (1024 * 1024),
        "max_file_kib": max_file_bytes / 1024,
        "elapsed": time.time() - t0,
    }
    print("\n=== ZERO-RANGE STATIC SHARDS EXPORT COMPLETE ===")
    print(f"Elapsed: {stats['elapsed']:.1f}s")
    print(f"Prompts: {stats['prompts']:,} ({stats['daily_eligible']:,} daily-eligible -> {stats['year_days']} non-repeating days)")
    print(f"Total answer links: {stats['total_answers']:,}")
    print(f"Files: {stats['total_files']:,} ({stats['chunk_files']} chunks + {stats['mega_files']} mega shards/summaries)")
    print(f"Total raw JSON size: {stats['total_raw_mib']:.2f} MiB | Largest single file: {stats['max_file_kib']:.1f} KiB")
    return stats


if __name__ == "__main__":
    export_from_sqlite()
