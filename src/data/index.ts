/**
 * Owns public exports for the prompt manifest, themed packs, and lazy chunk loader.
 * Does not fetch chunks directly or store runtime game state.
 */
export {
  PROMPT_MANIFEST,
  THEMED_PACKS,
  TOTAL_ANSWER_COUNT,
  YEAR_COVERAGE_DAYS,
} from './manifest';
export {
  PROMPT_META_BY_ID,
  getCachedPrompt,
  loadPrompt,
  parsePromptJson,
  preloadPrompts,
  type RawPromptEntry,
} from './promptLoader';
