import type { PromptCategory } from './types';

// Epoch chosen so 2026-11-26 resolves to Dive #134 (matching live krillion.io numbering)
export const KRILLION_EPOCH_ET = '2026-07-16';
export const DAILY_PROMPT_COUNT = 7;

export interface SchedulePromptItem {
  id: string;
  category: PromptCategory;
}

export function getEasternDateString(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);

  const year = parts.find((p) => p.type === 'year')?.value ?? '2026';
  const month = parts.find((p) => p.type === 'month')?.value ?? '11';
  const day = parts.find((p) => p.type === 'day')?.value ?? '26';
  return `${year}-${month}-${day}`;
}

function dateStringToUtcDayIndex(dateEt: string): number {
  const [y, m, d] = dateEt.split('-').map(Number);
  return Math.floor(Date.UTC(y, m - 1, d) / 86_400_000);
}

export function dateStringFromDiveNumber(diveNumber: number): string {
  const epochDays = dateStringToUtcDayIndex(KRILLION_EPOCH_ET);
  const targetMs = (epochDays + diveNumber - 1) * 86_400_000;
  const d = new Date(targetMs);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function getDiveNumberForDate(dateEt: string): number {
  const diff = dateStringToUtcDayIndex(dateEt) - dateStringToUtcDayIndex(KRILLION_EPOCH_ET);
  return Math.max(1, diff + 1);
}

export function getPreviousDateEt(dateEt: string): string {
  const prevDays = dateStringToUtcDayIndex(dateEt) - 1;
  const d = new Date(prevDays * 86_400_000);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function getMsUntilNextEasternMidnight(now: Date = new Date()): number {
  const etParts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(now);

  const hour = Number(etParts.find((p) => p.type === 'hour')?.value ?? '0') % 24;
  const minute = Number(etParts.find((p) => p.type === 'minute')?.value ?? '0');
  const second = Number(etParts.find((p) => p.type === 'second')?.value ?? '0');
  const elapsedMs = ((hour * 60 + minute) * 60 + second) * 1000 + now.getMilliseconds();
  return Math.max(1000, 86_400_000 - elapsedMs);
}

export function formatCountdown(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(totalSec / 3600)).padStart(2, '0');
  const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
  const s = String(totalSec % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffleInPlace<T>(arr: T[], rng: () => number): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

const CATEGORIES: PromptCategory[] = ['general', 'geography', 'movies', 'sports', 'words'];
const deckCache = new Map<string, SchedulePromptItem[]>();

/**
 * Build a deterministic full-cycle permutation deck so every prompt appears once
 * before any prompt repeats, while balancing categories across each 7-prompt day.
 */
function getCycleDeck<T extends SchedulePromptItem>(catalog: T[], cycleSeed = 20260716): T[] {
  const firstId = catalog[0]?.id ?? '';
  const lastId = catalog[catalog.length - 1]?.id ?? '';
  const cacheKey = `${catalog.length}:${firstId}:${lastId}:${cycleSeed}`;
  const cached = deckCache.get(cacheKey);
  if (cached) return cached as T[];

  const rng = mulberry32(cycleSeed);
  const buckets = new Map<PromptCategory, T[]>();
  for (const cat of CATEGORIES) {
    buckets.set(cat, []);
  }
  for (const item of catalog) {
    const list = buckets.get(item.category);
    if (list) list.push(item);
    else buckets.set(item.category, [item]);
  }
  for (const list of buckets.values()) {
    shuffleInPlace(list, rng);
  }

  const totalDays = Math.floor(catalog.length / DAILY_PROMPT_COUNT);
  const deck: T[] = [];
  const cursors = new Map<PromptCategory, number>();
  for (const cat of CATEGORIES) cursors.set(cat, 0);

  const remainingFor = (cat: PromptCategory) =>
    (buckets.get(cat)?.length ?? 0) - (cursors.get(cat) ?? 0);

  const takeOne = (cat: PromptCategory): T | null => {
    const list = buckets.get(cat);
    const idx = cursors.get(cat) ?? 0;
    if (!list || idx >= list.length) return null;
    cursors.set(cat, idx + 1);
    return list[idx];
  };

  for (let day = 0; day < totalDays; day++) {
    const dayItems: T[] = [];
    const dayCounts = new Map<PromptCategory, number>();

    // First pass: pick one from distinct available categories proportional to remaining pool
    const shuffledCats = shuffleInPlace([...CATEGORIES], rng);
    for (const cat of shuffledCats) {
      if (dayItems.length >= DAILY_PROMPT_COUNT) break;
      if (remainingFor(cat) > 0) {
        const picked = takeOne(cat);
        if (picked) {
          dayItems.push(picked);
          dayCounts.set(cat, (dayCounts.get(cat) ?? 0) + 1);
        }
      }
    }

    // Second pass: fill remaining slots favoring largest remaining pools (keeping variety)
    while (dayItems.length < DAILY_PROMPT_COUNT) {
      const candidates = CATEGORIES.filter((c) => remainingFor(c) > 0).sort((a, b) => {
        const remRatioA = remainingFor(a) / Math.max(1, buckets.get(a)?.length ?? 1);
        const remRatioB = remainingFor(b) / Math.max(1, buckets.get(b)?.length ?? 1);
        const countA = dayCounts.get(a) ?? 0;
        const countB = dayCounts.get(b) ?? 0;
        if (countA !== countB && (countA < 2 || countB < 2)) {
          return countA - countB;
        }
        return remRatioB - remRatioA;
      });
      if (candidates.length === 0) break;
      const picked = takeOne(candidates[0]);
      if (!picked) break;
      dayItems.push(picked);
      dayCounts.set(candidates[0], (dayCounts.get(candidates[0]) ?? 0) + 1);
    }

    // Shuffle prompt order within the day so categories appear in natural order
    shuffleInPlace(dayItems, rng);
    deck.push(...dayItems);
  }

  deckCache.set(cacheKey, deck);
  return deck;
}

export function getPromptsForDiveNumber<T extends SchedulePromptItem>(
  catalog: T[],
  diveNumber: number
): T[] {
  const cycleDays = Math.floor(catalog.length / DAILY_PROMPT_COUNT);
  if (cycleDays < 1) {
    return catalog.slice(0, DAILY_PROMPT_COUNT);
  }
  const deck = getCycleDeck(catalog);
  const dayIndex = (Math.max(1, diveNumber) - 1) % cycleDays;
  const start = dayIndex * DAILY_PROMPT_COUNT;
  return deck.slice(start, start + DAILY_PROMPT_COUNT);
}

export function pickUnlimitedPrompts<T extends SchedulePromptItem>(
  catalog: T[],
  recentPromptIds: string[] = [],
  count = DAILY_PROMPT_COUNT
): T[] {
  const exclude = new Set(recentPromptIds);
  const seed = Math.floor(Math.random() * 2_000_000_000) ^ Date.now();
  const rng = mulberry32(seed);
  const pool = catalog.filter((p) => !exclude.has(p.id));
  const source = pool.length >= count ? [...pool] : [...catalog];
  shuffleInPlace(source, rng);

  const chosen: T[] = [];
  const usedIds = new Set<string>();
  const categoryCount = new Map<string, number>();

  for (const prompt of source) {
    if (chosen.length >= count) break;
    const catCount = categoryCount.get(prompt.category) ?? 0;
    if (catCount < 2 || prompt.category === 'general') {
      chosen.push(prompt);
      usedIds.add(prompt.id);
      categoryCount.set(prompt.category, catCount + 1);
    }
  }

  for (const prompt of source) {
    if (chosen.length >= count) break;
    if (!usedIds.has(prompt.id)) {
      chosen.push(prompt);
      usedIds.add(prompt.id);
    }
  }

  return chosen;
}
