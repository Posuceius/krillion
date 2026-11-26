/**
 * Owns answer normalization, index construction, exact/alias lookup, and bounded Levenshtein matching.
 * Does not fetch prompt data or manage round timers.
 */
import { TIERS } from './tiers';
import type { AnswerEntry, MatchResult, Prompt } from './types';

interface IndexedVariant {
  normalized: string;
  entry: AnswerEntry;
}

export interface PromptIndex {
  exactMap: Map<string, AnswerEntry>;
  byLength: Map<number, IndexedVariant[]>;
}

export function normalizeAnswer(raw: string): string {
  return raw
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\+\+/g, ' plus plus')
    .replace(/#/g, ' sharp')
    .replace(/&/g, ' and ')
    .replace(/['’`]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function stripLeadingArticle(normalized: string): string {
  return normalized.replace(/^(the|a|an)\s+/, '').trim();
}

function pluralVariants(norm: string): string[] {
  const out = [norm];
  const stripped = stripLeadingArticle(norm);
  if (stripped && stripped !== norm) {
    out.push(stripped);
  }
  const baseList = [...out];
  for (const form of baseList) {
    if (form.length >= 4 && !form.includes(' ')) {
      if (form.endsWith('s') && !form.endsWith('ss')) {
        out.push(form.slice(0, -1));
      } else if (!form.endsWith('s')) {
        out.push(`${form}s`);
      }
      if (form.endsWith('es') && form.length >= 5) {
        out.push(form.slice(0, -2));
      }
    }
  }
  return Array.from(new Set(out));
}

export function levenshtein(a: string, b: string, maxDist = 3): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  if (Math.abs(m - n) > maxDist) return maxDist + 1;

  const prev = new Array<number>(n + 1);
  const curr = new Array<number>(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    let rowMin = i;
    const ca = a.charCodeAt(i - 1);
    for (let j = 1; j <= n; j++) {
      const cost = ca === b.charCodeAt(j - 1) ? 0 : 1;
      const val = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
      curr[j] = val;
      if (val < rowMin) rowMin = val;
    }
    if (rowMin > maxDist) return maxDist + 1;
    for (let j = 0; j <= n; j++) prev[j] = curr[j];
  }
  return prev[n];
}

export function buildPromptIndex(prompt: Prompt): PromptIndex {
  const exactMap = new Map<string, AnswerEntry>();
  const byLength = new Map<number, IndexedVariant[]>();

  for (const entry of prompt.answers) {
    const rawForms = [entry.canonical, ...(entry.aliases ?? [])];
    for (const raw of rawForms) {
      const norm = normalizeAnswer(raw);
      if (!norm) continue;
      for (const v of pluralVariants(norm)) {
        if (!exactMap.has(v)) {
          exactMap.set(v, entry);
          let bucket = byLength.get(v.length);
          if (!bucket) {
            bucket = [];
            byLength.set(v.length, bucket);
          }
          bucket.push({ normalized: v, entry });
        }
      }
    }
  }

  return { exactMap, byLength };
}

export function matchPromptAnswer(
  prompt: Prompt,
  rawInput: string,
  index?: PromptIndex,
  answerCorrectionsEnabled = true
): MatchResult {
  const norm = normalizeAnswer(rawInput);
  if (!norm) {
    return {
      kind: 'no_echo',
      rawInput,
      tier: 'miss',
      points: 0,
      depthMeters: 0,
      needsConfirmation: false,
    };
  }

  const idx = index ?? buildPromptIndex(prompt);
  const candidates = [norm, stripLeadingArticle(norm)].filter(Boolean);

  for (const cand of candidates) {
    const hit = idx.exactMap.get(cand);
    if (hit) {
      const canonicalNorm = normalizeAnswer(hit.canonical);
      const isExactCanonical = cand === canonicalNorm || norm === canonicalNorm;
      const tierDef = TIERS[hit.tier];
      return {
        kind: isExactCanonical ? 'exact' : 'alias',
        rawInput,
        canonical: hit.canonical,
        tier: hit.tier,
        points: tierDef.points,
        depthMeters: tierDef.depthMeters,
        needsConfirmation: false,
      };
    }
  }

  // Fuzzy typo check only for inputs >= 4 characters, scanning only length buckets within maxDist
  const stripped = stripLeadingArticle(norm);
  if (stripped.length >= 4) {
    const maxDist = stripped.length >= 7 ? 2 : 1;
    let bestDist = maxDist + 1;
    let bestEntry: AnswerEntry | null = null;
    let tied = false;

    for (let len = stripped.length - maxDist; len <= stripped.length + maxDist; len++) {
      const bucket = idx.byLength.get(len);
      if (!bucket) continue;
      for (let i = 0; i < bucket.length; i++) {
        const item = bucket[i];
        const dist = levenshtein(stripped, item.normalized, maxDist);
        if (dist <= maxDist) {
          if (dist < bestDist) {
            bestDist = dist;
            bestEntry = item.entry;
            tied = false;
          } else if (
            dist === bestDist &&
            bestEntry &&
            bestEntry.canonical !== item.entry.canonical
          ) {
            tied = true;
          }
        }
      }
    }

    if (bestEntry && (!tied || bestDist === 1)) {
      const tierDef = TIERS[bestEntry.tier];
      return {
        kind: 'fuzzy',
        rawInput,
        canonical: bestEntry.canonical,
        tier: bestEntry.tier,
        points: tierDef.points,
        depthMeters: tierDef.depthMeters,
        needsConfirmation: answerCorrectionsEnabled,
      };
    }
  }

  return {
    kind: 'no_echo',
    rawInput,
    tier: 'miss',
    points: 0,
    depthMeters: 0,
    needsConfirmation: false,
  };
}
