/**
 * Owns core domain TypeScript interfaces for prompts, tiers, dive runs, settings, and logbook state.
 * Does not contain runtime logic or UI state.
 */
export type TierId =
  | 'miss'
  | 'plankton'
  | 'tooclever'
  | 'schooler'
  | 'rare'
  | 'deepcut'
  | 'krillion';

export type AcceptedTierId = Exclude<TierId, 'miss'>;

export type PromptCategory = 'general' | 'words' | 'movies' | 'sports' | 'geography';

export interface AnswerEntry {
  canonical: string;
  tier: AcceptedTierId;
  aliases?: string[];
}

export interface PromptMeta {
  id: string;
  text: string;
  category: PromptCategory;
  answerCount: number;
  chunk: number;
}

export interface Prompt {
  id: string;
  text: string;
  category: PromptCategory;
  answers: AnswerEntry[];
}

export type DiveMode = 'daily' | 'archive' | 'unlimited' | 'pack';

export type BuddyId =
  | 'krill'
  | 'schooler'
  | 'squid'
  | 'angler'
  | 'evil_krill'
  | 'hackmanite'
  | 'fossil_krill'
  | 'mantis_shrimp'
  | 'leviathan';

export interface TierDefinition {
  id: TierId;
  label: string;
  shortLabel: string;
  points: number;
  depthMeters: number;
  emoji: string;
  flavor: string;
  color: string;
  colorblindColor: string;
}

export interface OceanZone {
  id: 'sunlight' | 'twilight' | 'midnight' | 'abyssal' | 'hadal';
  name: string;
  subtitle: string;
  minDepth: number;
  maxDepth: number;
  badgeColor: string;
}

export interface DepthMilestone {
  depth: number;
  label: string;
  isZoneHeader?: boolean;
}

export interface BuddyDefinition {
  id: BuddyId;
  name: string;
  requiredStreak: number;
  description: string;
}

export type MatchKind = 'exact' | 'alias' | 'fuzzy' | 'no_echo';

export interface MatchResult {
  kind: MatchKind;
  rawInput: string;
  canonical?: string;
  tier: TierId;
  points: number;
  depthMeters: number;
  needsConfirmation: boolean;
}

export interface RoundResult {
  promptId: string;
  promptText: string;
  rawAnswer: string;
  canonicalAnswer: string | null;
  tier: TierId;
  points: number;
  depthMeters: number;
  timedOut: boolean;
}

export interface DiveRunRecord {
  id: string;
  mode: DiveMode;
  label: string;
  diveNumber?: number;
  dateEt?: string;
  packId?: string;
  chapterIndex?: number;
  completedAt: string;
  rounds: RoundResult[];
  totalScore: number;
  maxScore: number;
  totalDepth: number;
}

export interface UserSettings {
  soundEnabled: boolean;
  lowPowerMode: boolean;
  colorblindMode: boolean;
  answerCorrections: boolean;
  clearRejectedEntries: boolean;
  shareLink: boolean;
}

export interface InProgressDive {
  mode: DiveMode;
  label: string;
  diveNumber?: number;
  dateEt?: string;
  packId?: string;
  chapterIndex?: number;
  promptIds: string[];
  rounds: RoundResult[];
  currentIndex: number;
}

export interface LogbookState {
  currentStreak: number;
  bestStreak: number;
  lastDailyDate: string | null;
  tierCounts: Record<TierId, number>;
  dailyCompleted: Record<string, DiveRunRecord>;
  archiveCompleted: Record<number, DiveRunRecord>;
  packCompleted: Record<string, DiveRunRecord>;
  unlimitedRuns: DiveRunRecord[];
}

export interface PersistedAppState {
  version: number;
  settings: UserSettings;
  equippedBuddy: BuddyId;
  logbook: LogbookState;
  inProgressDaily: InProgressDive | null;
}

export interface ThemedPackChapter {
  id: string;
  title: string;
  subtitle: string;
  promptIds: string[];
}

export interface ThemedPack {
  id: Exclude<PromptCategory, 'general'>;
  title: string;
  subtitle: string;
  unitLabel: string;
  accentColor: string;
  chapters: ThemedPackChapter[];
}
