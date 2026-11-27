/**
 * Owns automated integrity and lookup checks across the zero-Range hybrid static JSON shards, manifest parity, broad-trivia guarantees, and human-friendly matching.
 * Does not mutate repository files or run in browser bundles.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import {
  PROMPT_MANIFEST,
  PROMPT_META_BY_ID,
  THEMED_PACKS,
  TOTAL_ANSWER_COUNT,
  YEAR_COVERAGE_DAYS,
  clearRepositoryCacheForTests,
  loadPromptTierSamples,
  matchPromptAnswerRemote,
  prefetchPrompts,
  searchPromptAnswers,
  setJsonFetcherForTests,
} from './index';
import type { MegaSummary, RawEntry } from './promptRepository';

const DATA_DIR = resolve(process.cwd(), 'public', 'data');
const CHUNKS_DIR = join(DATA_DIR, 'chunks');
const MEGA_DIR = join(DATA_DIR, 'mega');
const LEGACY_DB_DIR = join(DATA_DIR, 'db');

const ALL_BUCKETS = [
  ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(97 + i)),
  '_',
];

beforeAll(() => {
  clearRepositoryCacheForTests();
  setJsonFetcherForTests(async (relativeDataPath) => {
    const filePath = join(DATA_DIR, relativeDataPath);
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  });
});

afterAll(() => {
  setJsonFetcherForTests(null);
  clearRepositoryCacheForTests();
});

describe('Zero-Range hybrid static shards & broad-trivia catalog (v1.4.0)', () => {
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

  it('removes legacy SQLite db dir and keeps all chunk and mega JSON files compact and valid', () => {
    expect(existsSync(LEGACY_DB_DIR)).toBe(false);

    const chunkFiles = readdirSync(CHUNKS_DIR).filter((f) => f.endsWith('.json'));
    expect(chunkFiles.length).toBeGreaterThan(100);

    const loadedChunks = new Map<string, Record<string, RawEntry[]>>();
    for (const file of chunkFiles) {
      const fullPath = join(CHUNKS_DIR, file);
      expect(statSync(fullPath).size).toBeLessThanOrEqual(1.5 * 1024 * 1024);
      const parsed = JSON.parse(readFileSync(fullPath, 'utf-8')) as Record<string, RawEntry[]>;
      loadedChunks.set(file.replace(/\.json$/, ''), parsed);
    }

    let summedAnswers = 0;
    const shardedMetas = PROMPT_MANIFEST.filter((m) => m.sharded);
    expect(shardedMetas.length).toBe(8);

    for (const meta of PROMPT_MANIFEST) {
      expect(meta.answerCount).toBeGreaterThanOrEqual(30);
      summedAnswers += meta.answerCount;

      if (meta.sharded) {
        expect(meta.chunk).toBeUndefined();
        const promptMegaDir = join(MEGA_DIR, meta.id);
        expect(existsSync(promptMegaDir)).toBe(true);

        for (const bucket of ALL_BUCKETS) {
          const bPath = join(promptMegaDir, `${bucket}.json`);
          expect(existsSync(bPath), `Missing bucket ${bucket}.json for ${meta.id}`).toBe(true);
          expect(statSync(bPath).size).toBeLessThanOrEqual(1.5 * 1024 * 1024);
          const bEntries = JSON.parse(readFileSync(bPath, 'utf-8')) as RawEntry[];
          expect(Array.isArray(bEntries)).toBe(true);
        }

        const summaryPath = join(promptMegaDir, 'summary.json');
        expect(existsSync(summaryPath)).toBe(true);
        const summary = JSON.parse(readFileSync(summaryPath, 'utf-8')) as MegaSummary;
        expect(summary.tierCounts).toHaveLength(6);
        let tierSum = 0;
        for (let t = 0; t < 6; t++) {
          expect(summary.tierCounts[t]).toBeGreaterThan(0);
          expect(summary.tierSamples[t].length).toBeGreaterThan(0);
          tierSum += summary.tierCounts[t];
        }
        expect(tierSum).toBe(meta.answerCount);
        expect(summary.topEntries.length).toBe(3000);
      } else {
        expect(meta.chunk).toBeDefined();
        const chunkObj = loadedChunks.get(meta.chunk!);
        expect(chunkObj, `Missing chunk ${meta.chunk} for ${meta.id}`).toBeDefined();
        const entries = chunkObj![meta.id];
        expect(entries, `Missing prompt ${meta.id} inside chunk ${meta.chunk}`).toBeDefined();
        expect(entries.length).toBe(meta.answerCount);

        const tierCounts = [0, 0, 0, 0, 0, 0];
        for (const [, tierIdx] of entries) {
          tierCounts[tierIdx] += 1;
        }
        for (let t = 0; t < 6; t++) {
          expect(tierCounts[t], `Empty tier ${t} in ${meta.id}`).toBeGreaterThan(0);
        }
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

  it('keeps wordcraft prompts strict (formLevel 0) and resolves fuzzy typos including first-letter mega typos', async () => {
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
    await prefetchPrompts([megaCity, island]);
    const t0 = performance.now();
    const hit = await matchPromptAnswerRemote(megaCity, 'Tokyo', true);
    const firstLetterTypo = await matchPromptAnswerRemote(megaCity, 'Zokyo', true);
    const miss = await matchPromptAnswerRemote(megaCity, 'zzzxqvkmnop', true);
    const elapsed = performance.now() - t0;
    expect(hit.kind).toBe('exact');
    expect(firstLetterTypo.kind).toBe('fuzzy');
    expect(firstLetterTypo.canonical).toBe('Tokyo');
    expect(miss.kind).toBe('no_echo');
    expect(elapsed).toBeLessThan(50);

    const samples12 = await loadPromptTierSamples(megaCity, 12);
    expect(samples12.plankton.total).toBeGreaterThan(1000);
    expect(samples12.plankton.items.length).toBe(12);

    const samples120 = await loadPromptTierSamples(megaCity, 120);
    expect(samples120.plankton.items.length).toBe(120);

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
