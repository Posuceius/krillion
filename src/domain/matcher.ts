/**
 * Owns answer normalization, human-friendly variant generation, shard bucket routing, index construction, exact/alias lookup, and bounded Levenshtein matching.
 * Does not fetch static shards or manage round timers.
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

const ROMAN_TOKENS: Record<string, string> = {
  ii: '2',
  iii: '3',
  iv: '4',
  v: '5',
  vi: '6',
  vii: '7',
  viii: '8',
  ix: '9',
  x: '10',
  xi: '11',
  xii: '12',
  xiii: '13',
  xiv: '14',
  xv: '15',
  xvi: '16',
  xvii: '17',
  xviii: '18',
  xix: '19',
  xx: '20',
};

const ABBREV_MAP: Record<string, string> = {
  mt: 'mount',
  st: 'saint',
  dr: 'doctor',
  ft: 'fort',
  pt: 'point',
};

const LEADING_AFFIXES = [
  'university of ',
  'island of ',
  'isle of ',
  'city of ',
  'town of ',
  'port of ',
  'mount ',
  'saint ',
  'lake ',
  'river ',
  'fort ',
  'mt ',
  'st ',
  'ft ',
  'fc ',
  'cf ',
  'ac ',
  'sc ',
];

const TRAILING_AFFIXES = [
  ' marine national park',
  ' international airport',
  ' national park',
  ' state park',
  ' archipelago',
  ' university',
  ' mountains',
  ' waterfall',
  ' peninsula',
  ' mountain',
  ' islands',
  ' volcano',
  ' glacier',
  ' stadium',
  ' airport',
  ' college',
  ' museum',
  ' castle',
  ' palace',
  ' desert',
  ' canyon',
  ' cavern',
  ' strait',
  ' bridge',
  ' island',
  ' cheese',
  ' river',
  ' atoll',
  ' falls',
  ' gorge',
  ' canal',
  ' arena',
  ' bread',
  ' sauce',
  ' pasta',
  ' grape',
  ' lake',
  ' peak',
  ' isle',
  ' city',
  ' town',
  ' cape',
  ' cave',
  ' park',
  ' soup',
  ' stew',
  ' wine',
  ' bay',
  ' gulf',
  ' mount',
  ' afc',
  ' fc',
  ' cf',
  ' ac',
  ' sc',
];

const AFFIX_STOPWORDS = new Set([
  'new', 'old', 'big', 'red', 'blue', 'white', 'black', 'green', 'gold',
  'east', 'west', 'north', 'south', 'upper', 'lower', 'great', 'little',
  'saint', 'san', 'los', 'las', 'sea', 'port', 'fort', 'long', 'high',
  'grand', 'royal', 'king', 'queen', 'clear', 'salt', 'rock', 'pine',
]);

const CLEAN_NORM_RE = /^[a-z0-9]+(?: [a-z0-9]+)*$/;

export function normalizeAnswer(raw: string): string {
  if (CLEAN_NORM_RE.test(raw)) return raw;
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

export function normalizeRomanNumerals(normalized: string): string {
  const parts = normalized.split(' ');
  let changed = false;
  const out = parts.map((tok) => {
    const rep = ROMAN_TOKENS[tok];
    if (rep) {
      changed = true;
      return rep;
    }
    return tok;
  });
  return changed ? out.join(' ') : normalized;
}

export function expandAbbreviations(normalized: string): string {
  const parts = normalized.split(' ');
  let changed = false;
  const out = parts.map((tok) => {
    const rep = ABBREV_MAP[tok];
    if (rep) {
      changed = true;
      return rep;
    }
    return tok;
  });
  return changed ? out.join(' ') : normalized;
}

function isCleanCore(core: string): boolean {
  if (!core || core.length < 3) return false;
  const words = core.split(' ');
  if (words.length === 1 && (core.length < 4 || AFFIX_STOPWORDS.has(core))) {
    return false;
  }
  return !words.every((w) => AFFIX_STOPWORDS.has(w));
}

export function stripCategoryAffixes(normalized: string): string[] {
  const results = new Set<string>();
  const seeds = [normalized, expandAbbreviations(normalized)];
  for (const cand of seeds) {
    const stripped = stripLeadingArticle(cand);
    for (const prefix of LEADING_AFFIXES) {
      if (stripped.startsWith(prefix)) {
        const core = stripLeadingArticle(stripped.slice(prefix.length).trim());
        if (isCleanCore(core)) results.add(core);
      }
    }
    for (const suffix of TRAILING_AFFIXES) {
      if (stripped.endsWith(suffix)) {
        const core = stripLeadingArticle(stripped.slice(0, stripped.length - suffix.length).trim());
        if (isCleanCore(core)) results.add(core);
      }
    }
  }
  return Array.from(results);
}

/** Generate normalized lookup candidates ordered from strictest to broadest. */
export function generateQueryCandidates(rawInput: string, formLevel: 0 | 1 | 2): string[] {
  const norm = normalizeAnswer(rawInput);
  if (!norm) return [];

  const out = new Set<string>();
  const add = (s: string) => {
    const trimmed = s.trim();
    if (trimmed) out.add(trimmed);
  };

  add(norm);
  const stripped = stripLeadingArticle(norm);
  if (stripped && stripped !== norm) add(stripped);

  if (formLevel === 0) {
    return Array.from(out);
  }

  const expanded = expandAbbreviations(norm);
  const roman = normalizeRomanNumerals(norm);
  const expRoman = normalizeRomanNumerals(expanded);
  for (const form of [expanded, roman, expRoman, stripLeadingArticle(expanded), stripLeadingArticle(roman), stripLeadingArticle(expRoman)]) {
    add(form);
  }

  for (const core of stripCategoryAffixes(norm)) {
    add(core);
  }

  return Array.from(out);
}

/** Generate short prefix/suffix keys to narrow indexed SQLite fuzzy scans. */
export function fuzzyLookupKeys(stripped: string): { p3Keys: string[]; s3Key: string } {
  const p3Keys = new Set<string>();
  if (stripped.length >= 3) {
    p3Keys.add(stripped.slice(0, 3));
    if (stripped.length >= 4) {
      // Handle a typo within the first 3 characters cleanly via deletion/transposition prefixes
      p3Keys.add(stripped.slice(1, 4));
      p3Keys.add(stripped[0] + stripped.slice(2, 4));
      p3Keys.add(stripped.slice(0, 2) + stripped[3]);
      p3Keys.add(stripped[1] + stripped[0] + stripped[2]);
    }
  }
  const s3Key = stripped.length >= 3 ? stripped.slice(-3) : stripped;
  return { p3Keys: Array.from(p3Keys), s3Key };
}

/** Route a normalized form to one of 27 static shard buckets (a..z or _). */
export function bucketKeyForNorm(norm: string): string {
  const stripped = stripLeadingArticle(norm) || norm;
  const ch = stripped[0];
  if (!ch) return '_';
  return ch >= 'a' && ch <= 'z' ? ch : '_';
}

export function pluralVariants(norm: string): string[] {
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
      if (form.endsWith('es') && lenCheck(form, 5)) {
        out.push(form.slice(0, -2));
      }
    }
  }
  return Array.from(new Set(out));
}

function lenCheck(s: string, minLen: number): boolean {
  return s.length >= minLen;
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
  const formLevel: 0 | 1 | 2 = prompt.category === 'words' ? 0 : 1;
  const candidates = generateQueryCandidates(rawInput, formLevel);

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
