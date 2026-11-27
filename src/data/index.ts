/**
 * Owns public exports for the prompt manifest, themed packs, and static SQLite repository.
 * Does not execute direct DOM operations or manage gameplay state.
 */
export {
  PROMPT_MANIFEST,
  THEMED_PACKS,
  TOTAL_ANSWER_COUNT,
  YEAR_COVERAGE_DAYS,
} from './manifest';
export {
  PROMPT_META_BY_ID,
  loadPromptTierSamples,
  matchPromptAnswerRemote,
  searchPromptAnswers,
  warmupDatabase,
} from './promptRepository';
export { setQueryExecutorForTests, type QueryExecutor } from './sqliteDb';
