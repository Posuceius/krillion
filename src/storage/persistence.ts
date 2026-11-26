/**
 * Owns versioned localStorage serialization, fallback defaults, and reset of settings/logbook state.
 * Does not compute streaks or scoring rules (see domain/scoring.ts).
 */
import type {
  BuddyId,
  LogbookState,
  PersistedAppState,
  UserSettings,
} from '../domain/types';

export const STORAGE_KEY = 'krillion_static_v1';

export const DEFAULT_SETTINGS: UserSettings = {
  soundEnabled: true,
  lowPowerMode: false,
  colorblindMode: false,
  answerCorrections: true,
  clearRejectedEntries: false,
  shareLink: false,
};

export function createEmptyLogbook(): LogbookState {
  return {
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
}

export function createDefaultState(): PersistedAppState {
  return {
    version: 1,
    settings: { ...DEFAULT_SETTINGS },
    equippedBuddy: 'krill',
    logbook: createEmptyLogbook(),
    inProgressDaily: null,
  };
}

const VALID_BUDDIES: ReadonlySet<BuddyId> = new Set([
  'krill',
  'schooler',
  'squid',
  'angler',
  'evil_krill',
  'hackmanite',
  'fossil_krill',
  'mantis_shrimp',
  'leviathan',
]);

export function loadPersistedState(): PersistedAppState {
  const fallback = createDefaultState();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<PersistedAppState>;
    if (!parsed || typeof parsed !== 'object') return fallback;

    const settings: UserSettings = {
      ...DEFAULT_SETTINGS,
      ...(parsed.settings ?? {}),
    };

    const rawLogbook = parsed.logbook ?? ({} as Partial<LogbookState>);
    const emptyLogbook = createEmptyLogbook();
    const logbook: LogbookState = {
      currentStreak:
        typeof rawLogbook.currentStreak === 'number' ? rawLogbook.currentStreak : 0,
      bestStreak: typeof rawLogbook.bestStreak === 'number' ? rawLogbook.bestStreak : 0,
      lastDailyDate:
        typeof rawLogbook.lastDailyDate === 'string' ? rawLogbook.lastDailyDate : null,
      tierCounts: {
        ...emptyLogbook.tierCounts,
        ...(rawLogbook.tierCounts ?? {}),
      },
      dailyCompleted: rawLogbook.dailyCompleted ?? {},
      archiveCompleted: rawLogbook.archiveCompleted ?? {},
      packCompleted: rawLogbook.packCompleted ?? {},
      unlimitedRuns: Array.isArray(rawLogbook.unlimitedRuns)
        ? rawLogbook.unlimitedRuns
        : [],
    };

    const equippedBuddy =
      parsed.equippedBuddy && VALID_BUDDIES.has(parsed.equippedBuddy)
        ? parsed.equippedBuddy
        : 'krill';

    return {
      version: 1,
      settings,
      equippedBuddy,
      logbook,
      inProgressDaily: parsed.inProgressDaily ?? null,
    };
  } catch {
    return fallback;
  }
}

export function savePersistedState(state: PersistedAppState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage quota or private-mode restrictions gracefully
  }
}

export function resetPersistedState(): PersistedAppState {
  const fresh = createDefaultState();
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
  return fresh;
}
