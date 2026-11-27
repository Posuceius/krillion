/**
 * Owns automated integrity and lookup checks across the chunked SQLite database, manifest parity, broad-trivia guarantees, and human-friendly matching.
 * Does not mutate repository files or run in browser bundles.
 */
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import {
  PROMPT_MANIFEST,
  PROMPT_META_BY_ID,
  THEMED_PACKS,
  TOTAL_ANSWER_COUNT,
  YEAR_COVERAGE_DAYS,
  loadPromptTierSamples,
  matchPromptAnswerRemote,
  searchPromptAnswers,
  setQueryExecutorForTests,
} from './index';

interface ChunkedDbConfig {
  serverMode: string;
  requestChunkSize: number;
  databaseLengthBytes: number;
  serverChunkSize: number;
  urlPrefix: string;
  suffixLength: number;
}

const DB_DIR = resolve(process.cwd(), 'public', 'data', 'db');

let tempDir: string | null = null;
let dbInstance: {
  prepare: (sql: string) => { all: (...params: unknown[]) => Record<string, unknown>[] };
  close: () => void;
} | null = null;
let dbConfig: ChunkedDbConfig;

beforeAll(async () => {
  dbConfig = JSON.parse(
    readFileSync(join(DB_DIR, 'config.json'), 'utf-8')
  ) as ChunkedDbConfig;

  const numParts = Math.ceil(
    dbConfig.databaseLengthBytes / dbConfig.serverChunkSize
  );
  const buffers: Buffer[] = [];
  for (let i = 0; i < numParts; i++) {
    const suffix = String(i).padStart(dbConfig.suffixLength, '0');
    const chunkPath = join(DB_DIR, `${dbConfig.urlPrefix}${suffix}`);
    const stat = statSync(chunkPath);
    expect(stat.size).toBeLessThanOrEqual(10.5 * 1024 * 1024);
    buffers.push(readFileSync(chunkPath));
  }

  const combined = Buffer.concat(buffers);
  expect(combined.length).toBe(dbConfig.databaseLengthBytes);
  expect(combined.length).toBeLessThan(220 * 1024 * 1024);

  tempDir = mkdtempSync(join(tmpdir(), 'krillion-db-test-'));
  const sqliteFile = join(tempDir, 'krillion.sqlite3');
  writeFileSync(sqliteFile, combined);

  const { DatabaseSync } = await import('node:sqlite');
  const db = new DatabaseSync(sqliteFile, { readOnly: true });
  dbInstance = db;

  setQueryExecutorForTests({
    async query(sql, params = []) {
      return db.prepare(sql).all(...params) as never[];
    },
  });
});

afterAll(() => {
  setQueryExecutorForTests(null);
  dbInstance?.close();
  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

describe('SQLite static database & broad-trivia catalog (v1.3.0)', () => {
  it('covers 365+ non-repeating daily dives using broad trivia without letter/wordcraft slices', () => {
    const dailyEligible = PROMPT_MANIFEST.filter((p) => !p.packOnly);
    expect(dailyEligible.length).toBeGreaterThanOrEqual(2555);
    expect(YEAR_COVERAGE_DAYS).toBe(Math.floor(dailyEligible.length / 7));
    expect(YEAR_COVERAGE_DAYS).toBeGreaterThanOrEqual(365);

    const ids = new Set(PROMPT_MANIFEST.map((p) => p.id));
    const texts = new Set(PROMPT_MANIFEST.map((p) => p.text.toLowerCase()));
    expect(ids.size).toBe(PROMPT_MANIFEST.length);
    expect(texts.size).toBe(PROMPT_MANIFEST.length);
    expect(TOTAL_ANSWER_COUNT).toBeGreaterThanOrEqual(2_000_000);

    for (const meta of dailyEligible) {
      expect(meta.text).not.toContain('starting with the letter ');
      expect(meta.text).not.toMatch(/^\s*Name a \d+-letter English word/);
    }
  });

  it('validates manifest parity, 6 tiers, and >= 30 answers per prompt inside SQLite', () => {
    expect(dbInstance).not.toBeNull();
    const promptRows = dbInstance!
      .prepare('SELECT id, slug, category, form_level, pack_only, answer_count FROM prompts')
      .all();
    expect(promptRows.length).toBe(PROMPT_MANIFEST.length);

    const bySlug = new Map(promptRows.map((r) => [String(r.slug), r]));
    const tierCountsRows = dbInstance!
      .prepare('SELECT prompt_id, tier, COUNT(*) AS cnt FROM prompt_answers GROUP BY prompt_id, tier')
      .all();

    const tiersByPrompt = new Map<number, Map<number, number>>();
    for (const row of tierCountsRows) {
      const pid = Number(row.prompt_id);
      let m = tiersByPrompt.get(pid);
      if (!m) {
        m = new Map<number, number>();
        tiersByPrompt.set(pid, m);
      }
      m.set(Number(row.tier), Number(row.cnt));
    }

    let summedAnswers = 0;
    for (const meta of PROMPT_MANIFEST) {
      const dbRow = bySlug.get(meta.id);
      expect(dbRow, `Missing ${meta.id} in SQLite`).toBeDefined();
      expect(Number(dbRow!.id)).toBe(meta.dbId);
      expect(Number(dbRow!.answer_count)).toBe(meta.answerCount);
      expect(meta.answerCount).toBeGreaterThanOrEqual(30);
      summedAnswers += meta.answerCount;

      const tMap = tiersByPrompt.get(meta.dbId);
      expect(tMap?.size).toBe(6);
      for (let t = 0; t < 6; t++) {
        expect(tMap!.get(t) ?? 0).toBeGreaterThan(0);
      }
    }
    expect(summedAnswers).toBe(TOTAL_ANSWER_COUNT);
  });

  it('scales mega-prompts and batched Wikidata pools to tens of thousands of answers', () => {
    const minCounts: Record<string, number> = {
      'geo-world-city': 80_000,
      'mov-any-movie': 80_000,
      'gen-tv-show': 25_000,
      'geo-island': 10_000,
      'geo-river': 10_000,
      'geo-city-am-usa': 12_000,
    };
    for (const [pid, minCnt] of Object.entries(minCounts)) {
      const meta = PROMPT_META_BY_ID[pid];
      expect(meta, `Missing mega-prompt ${pid}`).toBeDefined();
      expect(meta.answerCount).toBeGreaterThanOrEqual(minCnt);
    }
  });

  it('accepts surnames on person prompts (formLevel 2)', async () => {
    const composer = PROMPT_META_BY_ID['gen-composer'];
    const footballer = PROMPT_META_BY_ID['spt-footballer'];
    const director = PROMPT_META_BY_ID['mov-director'];
    const scientist = PROMPT_META_BY_ID['gen-scientist'];

    expect(composer.formLevel).toBe(2);
    expect(footballer.formLevel).toBe(2);

    const mozart = await matchPromptAnswerRemote(composer, 'Mozart');
    expect(mozart.kind).not.toBe('no_echo');
    expect(mozart.canonical).toContain('Mozart');

    const beethoven = await matchPromptAnswerRemote(composer, 'Beethoven');
    expect(beethoven.kind).not.toBe('no_echo');
    expect(beethoven.canonical).toContain('Beethoven');

    const messi = await matchPromptAnswerRemote(footballer, 'Messi');
    expect(messi.kind).not.toBe('no_echo');
    expect(messi.canonical).toBe('Lionel Messi');

    const ronaldo = await matchPromptAnswerRemote(footballer, 'Ronaldo');
    expect(ronaldo.kind).not.toBe('no_echo');

    const spielberg = await matchPromptAnswerRemote(director, 'Spielberg');
    expect(spielberg.kind).not.toBe('no_echo');
    expect(spielberg.canonical).toBe('Steven Spielberg');

    const einstein = await matchPromptAnswerRemote(scientist, 'Einstein');
    expect(einstein.kind).not.toBe('no_echo');
    expect(einstein.canonical).toBe('Albert Einstein');

    const daVinci = await matchPromptAnswerRemote(scientist, 'da Vinci');
    expect(daVinci.kind).not.toBe('no_echo');
    expect(daVinci.canonical).toBe('Leonardo da Vinci');
  });

  it('matches category affixes, abbreviations, Roman numerals, subtitles, and aliases', async () => {
    const mountain = PROMPT_META_BY_ID['geo-mountain'];
    for (const ans of ['Everest', 'Mt Everest', 'Fuji']) {
      const res = await matchPromptAnswerRemote(mountain, ans);
      expect(res.kind, `Expected ${ans} to match in geo-mountain`).not.toBe('no_echo');
    }

    const park = PROMPT_META_BY_ID['geo-national-park'];
    const yellowstone = await matchPromptAnswerRemote(park, 'Yellowstone National Park');
    expect(yellowstone.kind).not.toBe('no_echo');
    expect(yellowstone.canonical).toBe('Yellowstone');

    const lake = PROMPT_META_BY_ID['geo-lake'];
    const victoria = await matchPromptAnswerRemote(lake, 'Victoria');
    expect(victoria.kind).not.toBe('no_echo');

    const island = PROMPT_META_BY_ID['geo-island'];
    for (const ans of ['Bonaire', 'Boneiru', 'Bonaire Island', 'Aruba', 'Curaçao']) {
      const res = await matchPromptAnswerRemote(island, ans);
      expect(res.kind, `Expected ${ans} in geo-island`).not.toBe('no_echo');
    }

    const compound = PROMPT_META_BY_ID['gen-compound'];
    const aspirin = await matchPromptAnswerRemote(compound, 'acetylsalicylic acid');
    expect(aspirin.kind).toBe('alias');
    expect(aspirin.canonical).toBe('aspirin');

    const anyMovie = PROMPT_META_BY_ID['mov-any-movie'];
    const rocky2 = await matchPromptAnswerRemote(anyMovie, 'Rocky 2');
    expect(rocky2.kind).not.toBe('no_echo');
    const toyStoryIII = await matchPromptAnswerRemote(anyMovie, 'Toy Story III');
    expect(toyStoryIII.kind).not.toBe('no_echo');
    const lotr = await matchPromptAnswerRemote(anyMovie, 'Fellowship of the Ring');
    expect(lotr.kind).not.toBe('no_echo');
  });

  it('keeps wordcraft prompts strict (formLevel 0) and resolves indexed fuzzy typos quickly (< 50ms)', async () => {
    const wrd = PROMPT_META_BY_ID['wrd-palindrome'];
    expect(wrd.formLevel).toBe(0);

    const island = PROMPT_META_BY_ID['geo-island'];
    const bonaier = await matchPromptAnswerRemote(island, 'Bonaier', true);
    expect(bonaier.kind).toBe('fuzzy');
    expect(bonaier.canonical).toBe('Bonaire');

    const composer = PROMPT_META_BY_ID['gen-composer'];
    const mozrt = await matchPromptAnswerRemote(composer, 'Mozrt', true);
    expect(mozrt.kind).toBe('fuzzy');
    expect(mozrt.canonical).toContain('Mozart');

    const mountain = PROMPT_META_BY_ID['geo-mountain'];
    const everst = await matchPromptAnswerRemote(mountain, 'Everst', true);
    expect(everst.kind).toBe('fuzzy');
    expect(everst.canonical).toBe('Mount Everest');

    const megaCity = PROMPT_META_BY_ID['geo-world-city'];
    const t0 = performance.now();
    const hit = await matchPromptAnswerRemote(megaCity, 'Tokyo', true);
    const miss = await matchPromptAnswerRemote(megaCity, 'zzzxqvkmnop', true);
    const elapsed = performance.now() - t0;
    expect(hit.kind).toBe('exact');
    expect(miss.kind).toBe('no_echo');
    expect(elapsed).toBeLessThan(50);

    const samples = await loadPromptTierSamples(megaCity, 12);
    expect(samples.plankton.total).toBeGreaterThan(1000);
    expect(samples.plankton.items.length).toBe(12);

    const hits = await searchPromptAnswers(megaCity, 'toky', 10);
    expect(hits.some((h) => h.canonical === 'Tokyo')).toBe(true);
  });

  it('maps every themed pack chapter to valid manifest prompts', () => {
    expect(THEMED_PACKS).toHaveLength(4);
    for (const pack of THEMED_PACKS) {
      expect(pack.chapters).toHaveLength(5);
      for (const ch of pack.chapters) {
        expect(ch.promptIds).toHaveLength(5);
        for (const pid of ch.promptIds) {
          expect(PROMPT_META_BY_ID[pid]).toBeDefined();
        }
      }
    }
  });
});
