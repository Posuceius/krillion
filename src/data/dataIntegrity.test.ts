/**
 * Owns automated integrity checks across all 64 static prompt chunks and manifest metadata.
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

function loadAllChunksFromDisk(): Record<number, Record<string, RawPromptEntry>> {
  const chunks: Record<number, Record<string, RawPromptEntry>> = {};
  for (let cid = 0; cid < 64; cid++) {
    const fileNum = String(cid).padStart(2, '0');
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

describe('prompt catalog integrity (full-year 2,555+ prompts)', () => {
  it('covers at least 365 non-repeating daily dives (>= 2,555 unique prompts)', () => {
    expect(PROMPT_MANIFEST.length).toBeGreaterThanOrEqual(2555);
    expect(YEAR_COVERAGE_DAYS).toBeGreaterThanOrEqual(365);

    const ids = new Set(PROMPT_MANIFEST.map((p) => p.id));
    const texts = new Set(PROMPT_MANIFEST.map((p) => p.text.toLowerCase()));
    expect(ids.size).toBe(PROMPT_MANIFEST.length);
    expect(texts.size).toBe(PROMPT_MANIFEST.length);
    expect(TOTAL_ANSWER_COUNT).toBeGreaterThanOrEqual(350_000);
  });

  it('validates all 64 chunk files (every prompt has 6 tiers, >= 30 answers, zero collisions)', () => {
    const chunks = loadAllChunksFromDisk();
    const errors: string[] = [];
    let summedAnswers = 0;

    let totalChunkBytes = 0;
    for (let cid = 0; cid < 64; cid++) {
      const fileNum = String(cid).padStart(2, '0');
      const filePath = resolve(
        process.cwd(),
        'public',
        'data',
        'chunks',
        `chunk-${fileNum}.json`
      );
      totalChunkBytes += statSync(filePath).size;
    }
    expect(totalChunkBytes).toBeLessThan(25 * 1024 * 1024);

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
  });

  it('indexes and matches the largest enriched prompt quickly (< 100ms)', () => {
    const chunks = loadAllChunksFromDisk();
    const largestMeta = [...PROMPT_MANIFEST].sort(
      (a, b) => b.answerCount - a.answerCount
    )[0];
    const prompt = parsePromptJson(largestMeta, chunks[largestMeta.chunk][largestMeta.id]);

    const t0 = performance.now();
    const idx = buildPromptIndex(prompt);
    const sample = prompt.answers[prompt.answers.length - 1];
    const exact = matchPromptAnswer(prompt, sample.canonical, idx);
    const miss = matchPromptAnswer(prompt, 'zzzxqvkmnop', idx);
    const elapsed = performance.now() - t0;

    expect(exact.tier).toBe(sample.tier);
    expect(miss.kind).toBe('no_echo');
    expect(elapsed).toBeLessThan(100);
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
