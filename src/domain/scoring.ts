/**
 * Owns depth/score totals, daily streak transitions, buddy unlocks, and spoiler-free share formatting.
 * Does not persist state to localStorage directly.
 */
import { getPreviousDateEt } from './dailySchedule';
import { BUDDIES, BUDDY_ORDER, TIERS, getOceanZone } from './tiers';
import type { BuddyId, DiveRunRecord, LogbookState, RoundResult } from './types';

export function calculateTotals(rounds: RoundResult[]): {
  totalScore: number;
  totalDepth: number;
} {
  const totalScore = rounds.reduce((sum, r) => sum + r.points, 0);
  return {
    totalScore,
    totalDepth: totalScore * 10,
  };
}

export function getUnlockedBuddies(bestStreak: number): BuddyId[] {
  return BUDDY_ORDER.filter((id) => bestStreak >= BUDDIES[id].requiredStreak);
}

export function recordCompletedRun(
  logbook: LogbookState,
  run: DiveRunRecord
): { nextLogbook: LogbookState; newlyUnlockedBuddies: BuddyId[] } {
  const prevUnlocked = new Set(getUnlockedBuddies(logbook.bestStreak));
  const nextTierCounts = { ...logbook.tierCounts };
  for (const round of run.rounds) {
    nextTierCounts[round.tier] = (nextTierCounts[round.tier] ?? 0) + 1;
  }

  let nextStreak = logbook.currentStreak;
  let nextBestStreak = logbook.bestStreak;
  let nextLastDaily = logbook.lastDailyDate;
  const nextDailyCompleted = { ...logbook.dailyCompleted };
  const nextArchiveCompleted = { ...logbook.archiveCompleted };
  const nextPackCompleted = { ...logbook.packCompleted };
  let nextUnlimitedRuns = logbook.unlimitedRuns;

  if (run.mode === 'daily' && run.dateEt) {
    if (!nextDailyCompleted[run.dateEt]) {
      nextDailyCompleted[run.dateEt] = run;
      if (logbook.lastDailyDate === getPreviousDateEt(run.dateEt)) {
        nextStreak = logbook.currentStreak + 1;
      } else if (logbook.lastDailyDate === run.dateEt) {
        nextStreak = Math.max(1, logbook.currentStreak);
      } else {
        nextStreak = 1;
      }
      nextBestStreak = Math.max(logbook.bestStreak, nextStreak);
      nextLastDaily = run.dateEt;
    }
  } else if (run.mode === 'archive' && run.diveNumber !== undefined) {
    const existing = nextArchiveCompleted[run.diveNumber];
    if (!existing || run.totalScore >= existing.totalScore) {
      nextArchiveCompleted[run.diveNumber] = run;
    }
  } else if (run.mode === 'pack' && run.packId && run.chapterIndex !== undefined) {
    const key = `${run.packId}:${run.chapterIndex}`;
    const existing = nextPackCompleted[key];
    if (!existing || run.totalScore >= existing.totalScore) {
      nextPackCompleted[key] = run;
    }
  } else if (run.mode === 'unlimited') {
    nextUnlimitedRuns = [run, ...logbook.unlimitedRuns].slice(0, 30);
  }

  const nextLogbook: LogbookState = {
    currentStreak: nextStreak,
    bestStreak: nextBestStreak,
    lastDailyDate: nextLastDaily,
    tierCounts: nextTierCounts,
    dailyCompleted: nextDailyCompleted,
    archiveCompleted: nextArchiveCompleted,
    packCompleted: nextPackCompleted,
    unlimitedRuns: nextUnlimitedRuns,
  };

  const newlyUnlockedBuddies = getUnlockedBuddies(nextBestStreak).filter(
    (id) => !prevUnlocked.has(id)
  );

  return { nextLogbook, newlyUnlockedBuddies };
}

export function formatShareCard(run: DiveRunRecord, shareUrl?: string): string {
  const zone = getOceanZone(run.totalDepth);
  const emojis = run.rounds.map((r) => TIERS[r.tier].emoji).join('');
  const lines = [
    `KRILLION · ${run.label}`,
    `Depth: ${run.totalDepth.toLocaleString()}m (${zone.name})`,
    `${emojis}`,
    `Score: ${run.totalScore}/${run.maxScore}`,
  ];
  if (shareUrl) {
    lines.push(shareUrl);
  }
  return lines.join('\n');
}
