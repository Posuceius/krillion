/**
 * Owns pure unit tests for answer matching, full-year daily scheduling, streaks, and share formatting.
 * Does not test DOM components or browser rendering.
 */
import { describe, expect, it } from 'vitest';
import { PROMPT_MANIFEST } from '../data/manifest';
import {
  dateStringFromDiveNumber,
  getDiveNumberForDate,
  getPromptsForDiveNumber,
} from './dailySchedule';
import {
  buildPromptIndex,
  expandAbbreviations,
  generateQueryCandidates,
  matchPromptAnswer,
  normalizeAnswer,
  normalizeRomanNumerals,
  stripCategoryAffixes,
} from './matcher';
import { formatShareCard, recordCompletedRun } from './scoring';
import { TIERS, getOceanZone } from './tiers';
import type { DiveRunRecord, LogbookState, Prompt } from './types';

const samplePrompt: Prompt = {
  id: 'sample-mag',
  text: 'Name a magazine',
  category: 'general',
  answers: [
    { canonical: 'Vogue', tier: 'plankton', aliases: ['Vogue Magazine'] },
    { canonical: 'Time', tier: 'tooclever', aliases: ['Time Magazine'] },
    { canonical: 'Highlights', tier: 'schooler', aliases: ['Highlights for Children'] },
    { canonical: 'Monocle', tier: 'rare' },
    { canonical: 'Aperture', tier: 'deepcut' },
    { canonical: 'Cabaret Voltaire', tier: 'krillion' },
  ],
};

describe('matcher', () => {
  it('normalizes accents, punctuation, ampersands, and whitespace', () => {
    expect(normalizeAnswer('  Café  &  Crème! ')).toBe('cafe and creme');
  });

  it('matches exact canonical, aliases, and leading articles', () => {
    const idx = buildPromptIndex(samplePrompt);
    const exact = matchPromptAnswer(samplePrompt, 'highlights', idx);
    expect(exact.kind).toBe('exact');
    expect(exact.tier).toBe('schooler');
    expect(exact.points).toBe(30);
    expect(exact.depthMeters).toBe(300);

    const alias = matchPromptAnswer(samplePrompt, 'Highlights for Children', idx);
    expect(alias.kind).toBe('alias');
    expect(alias.canonical).toBe('Highlights');
  });

  it('proposes fuzzy typo correction when answerCorrections is enabled', () => {
    const idx = buildPromptIndex(samplePrompt);
    const fuzzy = matchPromptAnswer(samplePrompt, 'highlghts', idx, true);
    expect(fuzzy.kind).toBe('fuzzy');
    expect(fuzzy.canonical).toBe('Highlights');
    expect(fuzzy.needsConfirmation).toBe(true);

    const autoAccept = matchPromptAnswer(samplePrompt, 'highlghts', idx, false);
    expect(autoAccept.kind).toBe('fuzzy');
    expect(autoAccept.needsConfirmation).toBe(false);
  });

  it('normalizes Roman numerals, abbreviations, and category affixes', () => {
    expect(normalizeRomanNumerals('rocky ii')).toBe('rocky 2');
    expect(normalizeRomanNumerals('toy story iii')).toBe('toy story 3');
    expect(expandAbbreviations('mt everest')).toBe('mount everest');
    expect(expandAbbreviations('st lucia')).toBe('saint lucia');
    expect(stripCategoryAffixes('mount everest')).toContain('everest');
    expect(stripCategoryAffixes('yellowstone national park')).toContain('yellowstone');
    expect(generateQueryCandidates('Yellowstone National Park', 1)).toContain('yellowstone');
    expect(generateQueryCandidates('starting q', 0)).toEqual(['starting q']);
  });

  it('rejects unrelated gibberish as no_echo', () => {
    const idx = buildPromptIndex(samplePrompt);
    const miss = matchPromptAnswer(samplePrompt, 'asdfqwerty', idx, true);
    expect(miss.kind).toBe('no_echo');
    expect(miss.tier).toBe('miss');
    expect(miss.points).toBe(0);
  });
});

describe('dailySchedule', () => {
  it('maps 2026-11-26 to Dive #134 and round-trips dates', () => {
    expect(getDiveNumberForDate('2026-11-26')).toBe(134);
    expect(dateStringFromDiveNumber(134)).toBe('2026-11-26');
    expect(getDiveNumberForDate('2026-07-16')).toBe(1);
  });

  it('excludes packOnly prompts from daily dives', () => {
    const mockCatalog = [
      { id: 'pack-q', category: 'words' as const, packOnly: true },
      ...Array.from({ length: 14 }, (_, i) => ({
        id: `broad-${i}`,
        category: 'general' as const,
      })),
    ];
    for (let d = 1; d <= 2; d++) {
      const picks = getPromptsForDiveNumber(mockCatalog, d);
      expect(picks.some((p) => p.id === 'pack-q')).toBe(false);
    }
  });

  it('selects 7 distinct prompts deterministically without repeating across a full 365-day year', () => {
    const mockCatalog = Array.from({ length: 30 }, (_, i) => ({
      id: `p-${i}`,
      category: 'general' as const,
    }));
    const d10 = getPromptsForDiveNumber(mockCatalog, 10);
    const d10Again = getPromptsForDiveNumber(mockCatalog, 10);
    const d11 = getPromptsForDiveNumber(mockCatalog, 11);

    expect(d10).toHaveLength(7);
    expect(d10.map((p) => p.id)).toEqual(d10Again.map((p) => p.id));
    expect(new Set(d10.map((p) => p.id)).size).toBe(7);
    const overlap = d10.filter((p) => d11.some((q) => q.id === p.id));
    expect(overlap).toHaveLength(0);

    // Full-year non-repeating check on the real 2,567-prompt manifest starting from Dive #1 and Dive #134
    const yearFromDay1 = new Set<string>();
    for (let d = 1; d <= 365; d++) {
      const picks = getPromptsForDiveNumber(PROMPT_MANIFEST, d);
      expect(picks).toHaveLength(7);
      for (const p of picks) yearFromDay1.add(p.id);
    }
    expect(yearFromDay1.size).toBe(365 * 7);

    const yearFromToday = new Set<string>();
    for (let d = 134; d < 134 + 365; d++) {
      const picks = getPromptsForDiveNumber(PROMPT_MANIFEST, d);
      expect(picks).toHaveLength(7);
      for (const p of picks) yearFromToday.add(p.id);
    }
    expect(yearFromToday.size).toBe(365 * 7);
  });
});

describe('scoring and logbook', () => {
  const emptyLogbook: LogbookState = {
    currentStreak: 0,
    bestStreak: 0,
    lastDailyDate: null,
    tierCounts: {
      miss: 0,
      plankton: 0,
      tooclever: 0,
      schooler: 0,
      rare: 0,
      deepcut: 0,
      krillion: 0,
    },
    dailyCompleted: {},
    archiveCompleted: {},
    packCompleted: {},
    unlimitedRuns: [],
  };

  it('increments streak on consecutive daily dives and keeps archive separate', () => {
    const makeRun = (dateEt: string, diveNumber: number): DiveRunRecord => ({
      id: `daily-${diveNumber}`,
      mode: 'daily',
      label: `DAILY DIVE #${diveNumber}`,
      diveNumber,
      dateEt,
      completedAt: new Date().toISOString(),
      rounds: [
        {
          promptId: 'p1',
          promptText: 'Test',
          rawAnswer: 'Highlights',
          canonicalAnswer: 'Highlights',
          tier: 'schooler',
          points: 30,
          depthMeters: 300,
          timedOut: false,
        },
      ],
      totalScore: 30,
      maxScore: 700,
      totalDepth: 300,
    });

    const r1 = recordCompletedRun(emptyLogbook, makeRun('2026-11-25', 133));
    expect(r1.nextLogbook.currentStreak).toBe(1);
    const r2 = recordCompletedRun(r1.nextLogbook, makeRun('2026-11-26', 134));
    expect(r2.nextLogbook.currentStreak).toBe(2);

    const archiveRun: DiveRunRecord = {
      ...makeRun('2026-11-01', 109),
      id: 'archive-109',
      mode: 'archive',
      label: 'ARCHIVE DIVE #109',
    };
    const r3 = recordCompletedRun(r2.nextLogbook, archiveRun);
    expect(r3.nextLogbook.currentStreak).toBe(2);
    expect(r3.nextLogbook.archiveCompleted[109].totalScore).toBe(30);
  });

  it('formats spoiler-free share card with tier emojis and ocean zone', () => {
    expect(getOceanZone(4200).name).toBe('ABYSSAL ZONE');
    const card = formatShareCard(
      {
        id: 'daily-134',
        mode: 'daily',
        label: 'DIVE #134',
        completedAt: '2026-11-26T00:00:00Z',
        rounds: [
          {
            promptId: '1',
            promptText: 'A',
            rawAnswer: 'x',
            canonicalAnswer: 'X',
            tier: 'krillion',
            points: TIERS.krillion.points,
            depthMeters: TIERS.krillion.depthMeters,
            timedOut: false,
          },
          {
            promptId: '2',
            promptText: 'B',
            rawAnswer: 'y',
            canonicalAnswer: 'Y',
            tier: 'schooler',
            points: TIERS.schooler.points,
            depthMeters: TIERS.schooler.depthMeters,
            timedOut: false,
          },
        ],
        totalScore: 130,
        maxScore: 700,
        totalDepth: 1300,
      },
      'https://example.gitlab.io/krillion/'
    );
    expect(card).toContain('DIVE #134');
    expect(card).toContain('1,300m (MIDNIGHT ZONE)');
    expect(card).toContain('🦐🐟');
    expect(card).toContain('https://example.gitlab.io/krillion/');
  });
});
