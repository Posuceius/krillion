/**
 * Owns automated integrity checks across all 256 static prompt chunks, Bonaire/island coverage, fixed Wikidata categories, aliases, and manifest metadata.
 * Does not mutate repository data or run in production bundles.
 */
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  buildPromptIndex,
  matchPromptAnswer,
  normalizeAnswer,
} from '../domain/matcher';
import { ACCEPTED_TIER_ORDER } from '../domain/tiers';
import {
  PROMPT_MANIFEST,
  PROMPT_META_BY_ID,
  THEMED_PACKS,
  TOTAL_ANSWER_COUNT,
  YEAR_COVERAGE_DAYS,
  parsePromptJson,
  type RawPromptEntry,
} from './index';

const NUM_CHUNKS = 256;

function loadAllChunksFromDisk(): Record<number, Record<string, RawPromptEntry>> {
  const chunks: Record<number, Record<string, RawPromptEntry>> = {};
  for (let cid = 0; cid < NUM_CHUNKS; cid++) {
    const fileNum = String(cid).padStart(3, '0');
    const filePath = resolve(
      process.cwd(),
      'public',
      'data',
      'chunks',
      `chunk-${fileNum}.json`
    );
    chunks[cid] = JSON.parse(readFileSync(filePath, 'utf-8'));
  }
  return chunks;
}

describe('prompt catalog integrity (v1.2.0 expanded 4,100+ prompts & aliases)', () => {
  it('covers 570+ non-repeating daily dives (>= 4,000 unique prompts)', () => {
    expect(PROMPT_MANIFEST.length).toBeGreaterThanOrEqual(4000);
    expect(YEAR_COVERAGE_DAYS).toBeGreaterThanOrEqual(570);

    const ids = new Set(PROMPT_MANIFEST.map((p) => p.id));
    const texts = new Set(PROMPT_MANIFEST.map((p) => p.text.toLowerCase()));
    expect(ids.size).toBe(PROMPT_MANIFEST.length);
    expect(texts.size).toBe(PROMPT_MANIFEST.length);
    expect(TOTAL_ANSWER_COUNT).toBeGreaterThanOrEqual(1_100_000);
  });

  it('validates all 256 chunk files (6 tiers, >= 30 answers, >= 300k aliases, zero collisions)', () => {
    const chunks = loadAllChunksFromDisk();
    const errors: string[] = [];
    let summedAnswers = 0;
    let totalAliases = 0;

    let totalChunkBytes = 0;
    for (let cid = 0; cid < NUM_CHUNKS; cid++) {
      const fileNum = String(cid).padStart(3, '0');
      const filePath = resolve(
        process.cwd(),
        'public',
        'data',
        'chunks',
        `chunk-${fileNum}.json`
      );
      totalChunkBytes += statSync(filePath).size;
    }
    expect(totalChunkBytes).toBeLessThan(65 * 1024 * 1024);

    for (const meta of PROMPT_MANIFEST) {
      const chunkPayload = chunks[meta.chunk];
      const raw = chunkPayload?.[meta.id];
      if (!raw) {
        errors.push(`${meta.id}: missing from chunk-${meta.chunk}`);
        continue;
      }

      const prompt = parsePromptJson(meta, raw);
      if (prompt.answers.length !== meta.answerCount) {
        errors.push(
          `${meta.id}: manifest count ${meta.answerCount} != json count ${prompt.answers.length}`
        );
      }
      if (prompt.answers.length < 30) {
        errors.push(`${meta.id}: only ${prompt.answers.length} answers (need >= 30)`);
      }

      summedAnswers += prompt.answers.length;

      const seenTiers = new Set<string>();
      const normalizedSeen = new Map<string, { tier: string; canonical: string }>();

      for (const entry of prompt.answers) {
        seenTiers.add(entry.tier);
        totalAliases += entry.aliases?.length ?? 0;
        const forms = [entry.canonical, ...(entry.aliases ?? [])];
        for (const form of forms) {
          const norm = normalizeAnswer(form);
          if (!norm) {
            errors.push(`${meta.id}: empty normalized form "${form}"`);
            continue;
          }
          const prev = normalizedSeen.get(norm);
          if (prev && prev.tier !== entry.tier) {
            errors.push(
              `${meta.id}: collision "${norm}" in both ${prev.tier} (${prev.canonical}) and ${entry.tier} (${entry.canonical})`
            );
          } else if (!prev) {
            normalizedSeen.set(norm, { tier: entry.tier, canonical: entry.canonical });
          }
        }
      }

      for (const reqTier of ACCEPTED_TIER_ORDER) {
        if (!seenTiers.has(reqTier)) {
          errors.push(`${meta.id}: missing tier ${reqTier}`);
        }
      }
    }

    expect(errors).toEqual([]);
    expect(summedAnswers).toBe(TOTAL_ANSWER_COUNT);
    expect(totalAliases).toBeGreaterThanOrEqual(300_000);
  });

  it('includes Bonaire, Aruba, and Curacao across island and archipelago prompts', () => {
    const chunks = loadAllChunksFromDisk();
    for (const pid of ['geo-island', 'geo-archipelago']) {
      const meta = PROMPT_META_BY_ID[pid];
      expect(meta).toBeDefined();
      const prompt = parsePromptJson(meta, chunks[meta.chunk][pid]);
      const idx = buildPromptIndex(prompt);
      for (const ans of ['Bonaire', 'Aruba', 'Curaçao']) {
        const res = matchPromptAnswer(prompt, ans, idx);
        expect(res.kind).not.toBe('no_echo');
      }
    }

    const bMeta = PROMPT_META_BY_ID['geo-island-ltr-b'];
    expect(bMeta).toBeDefined();
    const bPrompt = parsePromptJson(bMeta, chunks[bMeta.chunk][bMeta.id]);
    expect(matchPromptAnswer(bPrompt, 'Bonaire').kind).not.toBe('no_echo');

    const aMeta = PROMPT_META_BY_ID['geo-island-ltr-a'];
    expect(aMeta).toBeDefined();
    const aPrompt = parsePromptJson(aMeta, chunks[aMeta.chunk][aMeta.id]);
    expect(matchPromptAnswer(aPrompt, 'Aruba').kind).not.toBe('no_echo');
  });

  it('verifies all 6 fixed Wikidata queries, fish, 1950s movies, stars, authors, and broadened Americas cities', () => {
    const chunks = loadAllChunksFromDisk();
    const minCounts: Record<string, number> = {
      'gen-nobel': 500,
      'gen-compound': 1000,
      'gen-grape': 500,
      'gen-vg-strategy': 500,
      'gen-vg-horror': 150,
      'gen-fish': 1000,
      'mov-decade-1950s': 800,
      'gen-star': 300,
      'gen-author': 500,
      'geo-city-am-brazil': 1000,
      'geo-city-am-colombia': 500,
      'geo-city-am-chile': 200,
      'geo-city-am-usa': 2000,
    };

    for (const [pid, minCount] of Object.entries(minCounts)) {
      const meta = PROMPT_META_BY_ID[pid];
      expect(meta, `Expected manifest entry for ${pid}`).toBeDefined();
      expect(meta.answerCount).toBeGreaterThanOrEqual(minCount);
    }

    const cityChecks: Array<[string, string[]]> = [
      ['geo-city-am-brazil', ['São Paulo', 'Rio de Janeiro']],
      ['geo-city-am-colombia', ['Bogotá']],
      ['geo-city-am-chile', ['Santiago']],
    ];
    for (const [pid, expectedNames] of cityChecks) {
      const meta = PROMPT_META_BY_ID[pid];
      const prompt = parsePromptJson(meta, chunks[meta.chunk][pid]);
      const idx = buildPromptIndex(prompt);
      for (const cityName of expectedNames) {
        expect(matchPromptAnswer(prompt, cityName, idx).kind).not.toBe('no_echo');
      }
    }
  });

  it('matches Wikidata English skos:altLabel aliases end-to-end', () => {
    const chunks = loadAllChunksFromDisk();

    const islandMeta = PROMPT_META_BY_ID['geo-island'];
    const islandPrompt = parsePromptJson(islandMeta, chunks[islandMeta.chunk][islandMeta.id]);
    const islandIdx = buildPromptIndex(islandPrompt);
    const boneiruMatch = matchPromptAnswer(islandPrompt, 'Boneiru', islandIdx);
    expect(boneiruMatch.kind).toBe('alias');
    expect(boneiruMatch.canonical).toBe('Bonaire');

    const compMeta = PROMPT_META_BY_ID['gen-compound'];
    const compPrompt = parsePromptJson(compMeta, chunks[compMeta.chunk][compMeta.id]);
    const compIdx = buildPromptIndex(compPrompt);
    const aspirinAlias = matchPromptAnswer(compPrompt, 'acetylsalicylic acid', compIdx);
    expect(aspirinAlias.kind).toBe('alias');
    expect(aspirinAlias.canonical).toBe('aspirin');
    const ethanolAlias = matchPromptAnswer(compPrompt, 'ethyl alcohol', compIdx);
    expect(ethanolAlias.kind).toBe('alias');
    expect(ethanolAlias.canonical).toBe('ethanol');

    const usaMeta = PROMPT_META_BY_ID['geo-city-am-usa'];
    const usaPrompt = parsePromptJson(usaMeta, chunks[usaMeta.chunk][usaMeta.id]);
    const usaIdx = buildPromptIndex(usaPrompt);
    for (const nyAlias of ['NY City', 'City of New York']) {
      const nyMatch = matchPromptAnswer(usaPrompt, nyAlias, usaIdx);
      expect(nyMatch.kind).toBe('alias');
      expect(nyMatch.canonical).toBe('New York City');
    }
  });

  it('indexes and matches the largest enriched prompt quickly (< 200ms)', () => {
    const chunks = loadAllChunksFromDisk();
    const largestMeta = [...PROMPT_MANIFEST].sort(
      (a, b) => b.answerCount - a.answerCount
    )[0];
    expect(largestMeta.answerCount).toBeGreaterThanOrEqual(6000);
    const prompt = parsePromptJson(largestMeta, chunks[largestMeta.chunk][largestMeta.id]);

    const t0 = performance.now();
    const idx = buildPromptIndex(prompt);
    const sample = prompt.answers[prompt.answers.length - 1];
    const exact = matchPromptAnswer(prompt, sample.canonical, idx);
    const miss = matchPromptAnswer(prompt, 'zzzxqvkmnop', idx);
    const elapsed = performance.now() - t0;

    expect(exact.tier).toBe(sample.tier);
    expect(miss.kind).toBe('no_echo');
    expect(elapsed).toBeLessThan(200);
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
