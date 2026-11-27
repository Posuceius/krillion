/**
 * Owns public exports for the prompt manifest, themed packs, and zero-Range static shard repository.
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
  clearRepositoryCacheForTests,
  loadPromptTierSamples,
  matchPromptAnswerRemote,
  prefetchPrompts,
  searchPromptAnswers,
  setJsonFetcherForTests,
  type JsonFetcher,
} from './promptRepository';
