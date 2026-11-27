/**
 * Owns zero-Range static JSON shard fetching, in-memory indexing, human-friendly answer matching, tier sampling, and search.
 * Does not manage round timers, localStorage persistence, or React UI state.
 */
import {
  bucketKeyForNorm,
  expandAbbreviations,
  generateQueryCandidates,
  levenshtein,
  normalizeAnswer,
  normalizeRomanNumerals,
  pluralVariants,
  stripLeadingArticle,
} from '../domain/matcher';
import { ACCEPTED_TIER_ORDER, TIERS } from '../domain/tiers';
import type { AcceptedTierId, MatchResult, PromptMeta } from '../domain/types';
import { PROMPT_MANIFEST } from './manifest';

export const PROMPT_META_BY_ID: Record<string, PromptMeta> = Object.fromEntries(
  PROMPT_MANIFEST.map((m) => [m.id, m])
);

export type RawEntry = [canonical: string, tierIdx: number, extraForms?: string[]];

export interface MegaSummary {
  tierCounts: number[];
  tierSamples: string[][];
  topEntries: RawEntry[];
}

export type JsonFetcher = (relativeDataPath: string) => Promise<unknown>;

interface IndexedEntry {
  rank: number;
  canonical: string;
  tierIdx: number;
}

interface FuzzyTarget {
  target: string;
  canonical: string;
  tierIdx: number;
}

interface ShardIndex {
  entries: RawEntry[];
  exactMap: Map<string, IndexedEntry>;
  aliasMap: Map<string, IndexedEntry>;
  fuzzyByLen: Map<number, FuzzyTarget[]> | null;
}

const FUZZY_TOP_LIMIT = 3000;

const TIER_BY_IDX: AcceptedTierId[] = [
  'plankton',
  'tooclever',
  'schooler',
  'rare',
  'deepcut',
  'krillion',
];

let customFetcher: JsonFetcher | null = null;
const chunkCache = new Map<string, Promise<Record<string, RawEntry[]>>>();
const megaShardCache = new Map<string, Promise<RawEntry[]>>();
const megaSummaryCache = new Map<string, Promise<MegaSummary>>();
const indexCache = new Map<string, ShardIndex>();

export function setJsonFetcherForTests(fetcher: JsonFetcher | null): void {
  customFetcher = fetcher;
}

export function clearRepositoryCacheForTests(): void {
  chunkCache.clear();
  megaShardCache.clear();
  megaSummaryCache.clear();
  indexCache.clear();
}

async function fetchDataJson<T>(relativeDataPath: string): Promise<T> {
  if (customFetcher) {
    return (await customFetcher(relativeDataPath)) as T;
  }
  const url = new URL(`./data/${relativeDataPath}`, document.baseURI).toString();
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Failed to fetch ./data/${relativeDataPath}: HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

function loadChunk(chunkName: string): Promise<Record<string, RawEntry[]>> {
  let pending = chunkCache.get(chunkName);
  if (!pending) {
    pending = fetchDataJson<Record<string, RawEntry[]>>(`chunks/${chunkName}.json`).catch((err) => {
      chunkCache.delete(chunkName);
      throw err;
    });
    chunkCache.set(chunkName, pending);
  }
  return pending;
}

function loadMegaShard(promptId: string, bucket: string): Promise<RawEntry[]> {
  const key = `${promptId}/${bucket}`;
  let pending = megaShardCache.get(key);
  if (!pending) {
    pending = fetchDataJson<RawEntry[]>(`mega/${promptId}/${bucket}.json`).catch((err) => {
      megaShardCache.delete(key);
      throw err;
    });
    megaShardCache.set(key, pending);
  }
  return pending;
}

function loadMegaSummary(promptId: string): Promise<MegaSummary> {
  let pending = megaSummaryCache.get(promptId);
  if (!pending) {
    pending = fetchDataJson<MegaSummary>(`mega/${promptId}/summary.json`).catch((err) => {
      megaSummaryCache.delete(promptId);
      throw err;
    });
    megaSummaryCache.set(promptId, pending);
  }
  return pending;
}

function buildShardIndex(entries: RawEntry[], formLevel: 0 | 1 | 2): ShardIndex {
  const exactMap = new Map<string, IndexedEntry>();
  const aliasMap = new Map<string, IndexedEntry>();

  for (let rank = 0; rank < entries.length; rank++) {
    const [canonical, tierIdx, extraForms] = entries[rank];
    const item: IndexedEntry = { rank, canonical, tierIdx };

    const cnorm = normalizeAnswer(canonical);
    if (cnorm) {
      for (const v of pluralVariants(cnorm)) {
        if (!exactMap.has(v)) exactMap.set(v, item);
      }
      if (formLevel >= 1) {
        const rCnorm = normalizeRomanNumerals(cnorm);
        if (rCnorm !== cnorm) {
          for (const v of pluralVariants(rCnorm)) {
            if (!exactMap.has(v)) exactMap.set(v, item);
          }
        }
        const aCnorm = expandAbbreviations(cnorm);
        if (aCnorm !== cnorm) {
          for (const v of pluralVariants(aCnorm)) {
            if (!exactMap.has(v)) exactMap.set(v, item);
          }
        }
      }
    }

    if (formLevel >= 1 && extraForms) {
      for (let j = 0; j < extraForms.length; j++) {
        const form = extraForms[j];
        if (form && !aliasMap.has(form)) {
          aliasMap.set(form, item);
        }
      }
    }
  }

  return { entries, exactMap, aliasMap, fuzzyByLen: null };
}

async function getNormalIndex(meta: PromptMeta): Promise<ShardIndex> {
  const cached = indexCache.get(meta.id);
  if (cached) return cached;

  if (!meta.chunk) {
    throw new Error(`Prompt ${meta.id} missing chunk name`);
  }
  const chunk = await loadChunk(meta.chunk);
  const entries = chunk[meta.id];
  if (!entries) {
    throw new Error(`Prompt ${meta.id} missing inside chunk ${meta.chunk}`);
  }
  const built = buildShardIndex(entries, meta.formLevel);
  indexCache.set(meta.id, built);
  return built;
}

async function getMegaShardIndex(meta: PromptMeta, bucket: string): Promise<ShardIndex> {
  const cacheKey = `${meta.id}:${bucket}`;
  const cached = indexCache.get(cacheKey);
  if (cached) return cached;

  const entries = await loadMegaShard(meta.id, bucket);
  const built = buildShardIndex(entries, meta.formLevel);
  indexCache.set(cacheKey, built);
  return built;
}

function getFuzzyByLen(
  cacheKey: string,
  entries: RawEntry[],
  formLevel: 0 | 1 | 2
): Map<number, FuzzyTarget[]> {
  const cached = indexCache.get(cacheKey);
  if (cached?.fuzzyByLen) return cached.fuzzyByLen;

  const byLen = new Map<number, FuzzyTarget[]>();
  const addTarget = (target: string, canonical: string, tierIdx: number) => {
    if (!target) return;
    let bucket = byLen.get(target.length);
    if (!bucket) {
      bucket = [];
      byLen.set(target.length, bucket);
    }
    bucket.push({ target, canonical, tierIdx });
  };

  const limit = Math.min(entries.length, FUZZY_TOP_LIMIT);
  // Register primary canonical stripped forms before aliases/affixes so exact forms win ties at rank order
  for (let i = 0; i < limit; i++) {
    const [canonical, tierIdx] = entries[i];
    const cnorm = normalizeAnswer(canonical);
    const target = stripLeadingArticle(cnorm) || cnorm;
    addTarget(target, canonical, tierIdx);
  }
  if (formLevel >= 1) {
    for (let i = 0; i < limit; i++) {
      const [canonical, tierIdx, extraForms] = entries[i];
      if (!extraForms) continue;
      for (let j = 0; j < extraForms.length; j++) {
        addTarget(extraForms[j], canonical, tierIdx);
      }
    }
  }

  if (cached) {
    cached.fuzzyByLen = byLen;
  } else {
    indexCache.set(cacheKey, {
      entries,
      exactMap: new Map(),
      aliasMap: new Map(),
      fuzzyByLen: byLen,
    });
  }
  return byLen;
}

function findBestFuzzyMatch(
  stripped: string,
  byLen: Map<number, FuzzyTarget[]>,
  maxDist: number
): FuzzyTarget | null {
  let bestDist = maxDist + 1;
  let bestHit: FuzzyTarget | null = null;
  let tied = false;

  for (let len = stripped.length - maxDist; len <= stripped.length + maxDist; len++) {
    const bucket = byLen.get(len);
    if (!bucket) continue;
    for (let i = 0; i < bucket.length; i++) {
      const item = bucket[i];
      const dist = levenshtein(stripped, item.target, maxDist);
      if (dist <= maxDist) {
        if (dist < bestDist) {
          bestDist = dist;
          bestHit = item;
          tied = false;
        } else if (
          dist === bestDist &&
          bestHit &&
          bestHit.canonical !== item.canonical
        ) {
          tied = true;
        }
      }
    }
  }

  if (bestHit && (!tied || bestDist === 1)) {
    return bestHit;
  }
  return null;
}

function buildAcceptedResult(
  kind: 'exact' | 'alias' | 'fuzzy',
  rawInput: string,
  canonical: string,
  tierIdx: number,
  needsConfirmation: boolean
): MatchResult {
  const tierId = TIER_BY_IDX[tierIdx] ?? 'plankton';
  const tierDef = TIERS[tierId];
  return {
    kind,
    rawInput,
    canonical,
    tier: tierId,
    points: tierDef.points,
    depthMeters: tierDef.depthMeters,
    needsConfirmation,
  };
}

function noEchoResult(rawInput: string): MatchResult {
  return {
    kind: 'no_echo',
    rawInput,
    tier: 'miss',
    points: 0,
    depthMeters: 0,
    needsConfirmation: false,
  };
}

export async function prefetchPrompts(prompts: PromptMeta[]): Promise<void> {
  const chunks = new Set<string>();
  const megaIds = new Set<string>();
  for (const meta of prompts) {
    if (meta.sharded) {
      megaIds.add(meta.id);
    } else if (meta.chunk) {
      chunks.add(meta.chunk);
    }
  }
  await Promise.all([
    ...Array.from(chunks, (c) => loadChunk(c)),
    ...Array.from(megaIds, (id) => loadMegaSummary(id)),
  ]);
}

function pickBestHit(
  candidates: string[],
  lookup: (cand: string) => IndexedEntry | undefined
): IndexedEntry | null {
  let best: IndexedEntry | null = null;
  for (const cand of candidates) {
    const hit = lookup(cand);
    if (hit && (!best || hit.rank < best.rank)) {
      best = hit;
    }
  }
  return best;
}

export async function matchPromptAnswerRemote(
  meta: PromptMeta,
  rawInput: string,
  answerCorrectionsEnabled = true
): Promise<MatchResult> {
  const norm = normalizeAnswer(rawInput);
  if (!norm) return noEchoResult(rawInput);

  const candidates = generateQueryCandidates(rawInput, meta.formLevel);
  if (meta.sharded) {
    const bucketKeys = Array.from(new Set(candidates.map(bucketKeyForNorm)));
    const bucketEntries = await Promise.all(
      bucketKeys.map(async (b) => [b, await getMegaShardIndex(meta, b)] as const)
    );
    const byBucket = new Map(bucketEntries);

    const exactHit = pickBestHit(candidates, (c) => byBucket.get(bucketKeyForNorm(c))?.exactMap.get(c));
    if (exactHit) {
      const kind = normalizeAnswer(exactHit.canonical) === norm ? 'exact' : 'alias';
      return buildAcceptedResult(kind, rawInput, exactHit.canonical, exactHit.tierIdx, false);
    }
    const aliasHit = pickBestHit(candidates, (c) => byBucket.get(bucketKeyForNorm(c))?.aliasMap.get(c));
    if (aliasHit) {
      return buildAcceptedResult('alias', rawInput, aliasHit.canonical, aliasHit.tierIdx, false);
    }
  } else {
    const idx = await getNormalIndex(meta);
    const exactHit = pickBestHit(candidates, (c) => idx.exactMap.get(c));
    if (exactHit) {
      const kind = normalizeAnswer(exactHit.canonical) === norm ? 'exact' : 'alias';
      return buildAcceptedResult(kind, rawInput, exactHit.canonical, exactHit.tierIdx, false);
    }
    const aliasHit = pickBestHit(candidates, (c) => idx.aliasMap.get(c));
    if (aliasHit) {
      return buildAcceptedResult('alias', rawInput, aliasHit.canonical, aliasHit.tierIdx, false);
    }
  }

  const stripped = stripLeadingArticle(norm);
  if (stripped.length >= 4) {
    const maxDist = stripped.length >= 7 ? 2 : 1;
    let fuzzyByLen: Map<number, FuzzyTarget[]>;
    if (meta.sharded) {
      const summary = await loadMegaSummary(meta.id);
      fuzzyByLen = getFuzzyByLen(`${meta.id}:summary`, summary.topEntries, meta.formLevel);
    } else {
      const idx = await getNormalIndex(meta);
      fuzzyByLen = getFuzzyByLen(meta.id, idx.entries, meta.formLevel);
    }

    const fuzzyHit = findBestFuzzyMatch(stripped, fuzzyByLen, maxDist);
    if (fuzzyHit) {
      return buildAcceptedResult(
        'fuzzy',
        rawInput,
        fuzzyHit.canonical,
        fuzzyHit.tierIdx,
        answerCorrectionsEnabled
      );
    }
  }

  return noEchoResult(rawInput);
}

export async function loadPromptTierSamples(
  meta: PromptMeta,
  limitPerTier = 12
): Promise<Record<AcceptedTierId, { total: number; items: string[] }>> {
  const out = {} as Record<AcceptedTierId, { total: number; items: string[] }>;
  for (const tid of ACCEPTED_TIER_ORDER) {
    out[tid] = { total: 0, items: [] };
  }

  if (meta.sharded) {
    const summary = await loadMegaSummary(meta.id);
    for (let i = 0; i < ACCEPTED_TIER_ORDER.length; i++) {
      const tid = ACCEPTED_TIER_ORDER[i];
      out[tid].total = summary.tierCounts[i] ?? 0;
      out[tid].items = (summary.tierSamples[i] ?? []).slice(0, limitPerTier);
    }
    return out;
  }

  const idx = await getNormalIndex(meta);
  for (let i = 0; i < idx.entries.length; i++) {
    const [canonical, tierIdx] = idx.entries[i];
    const tid = TIER_BY_IDX[tierIdx];
    if (!tid) continue;
    out[tid].total += 1;
    if (out[tid].items.length < limitPerTier) {
      out[tid].items.push(canonical);
    }
  }
  return out;
}

export async function searchPromptAnswers(
  meta: PromptMeta,
  rawQuery: string,
  limit = 60
): Promise<Array<{ canonical: string; tier: AcceptedTierId }>> {
  const norm = normalizeAnswer(rawQuery);
  if (!norm) return [];
  const strippedQuery = stripLeadingArticle(norm) || norm;

  const entries = meta.sharded
    ? (await getMegaShardIndex(meta, bucketKeyForNorm(norm))).entries
    : (await getNormalIndex(meta)).entries;

  const results: Array<{ canonical: string; tier: AcceptedTierId }> = [];
  const seen = new Set<string>();

  for (let i = 0; i < entries.length && results.length < limit; i++) {
    const [canonical, tierIdx, extraForms] = entries[i];
    if (seen.has(canonical)) continue;
    const cnorm = normalizeAnswer(canonical);
    const cstripped = stripLeadingArticle(cnorm);
    const matchedCanonical =
      cnorm.startsWith(norm) || (cstripped !== cnorm && cstripped.startsWith(strippedQuery));
    const matchedExtra =
      meta.formLevel >= 1 &&
      !!extraForms?.some((f) => f.startsWith(norm) || f.startsWith(strippedQuery));

    if (matchedCanonical || matchedExtra) {
      seen.add(canonical);
      results.push({
        canonical,
        tier: TIER_BY_IDX[tierIdx] ?? 'plankton',
      });
    }
  }

  return results;
}
