/**
 * Owns lazy fetching, caching, and parsing of static prompt JSON chunks under ./data/chunks/.
 * Does not define prompt metadata (see manifest.ts) or schedule dives.
 */
import type { AcceptedTierId, AnswerEntry, Prompt, PromptMeta } from '../domain/types';
import { PROMPT_MANIFEST } from './manifest';

export const PROMPT_META_BY_ID: Record<string, PromptMeta> = Object.fromEntries(
  PROMPT_MANIFEST.map((m) => [m.id, m])
);

export interface RawPromptEntry {
  tiers: Record<AcceptedTierId, Array<string | [string, ...string[]]>>;
}

type RawChunkPayload = Record<string, RawPromptEntry>;

const TIER_KEYS: AcceptedTierId[] = [
  'plankton',
  'tooclever',
  'schooler',
  'rare',
  'deepcut',
  'krillion',
];

const promptCache = new Map<string, Prompt>();
const chunkCache = new Map<number, RawChunkPayload>();
const inflightChunks = new Map<number, Promise<RawChunkPayload>>();

export function parsePromptJson(meta: PromptMeta, raw: RawPromptEntry): Prompt {
  const answers: AnswerEntry[] = [];
  for (const tier of TIER_KEYS) {
    const list = raw.tiers[tier] ?? [];
    for (const item of list) {
      if (typeof item === 'string') {
        answers.push({ canonical: item, tier });
      } else {
        const [canonical, ...aliases] = item;
        answers.push({ canonical, tier, aliases });
      }
    }
  }
  return {
    id: meta.id,
    text: meta.text,
    category: meta.category,
    answers,
  };
}

export function getCachedPrompt(id: string): Prompt | undefined {
  return promptCache.get(id);
}

async function loadChunk(chunkId: number): Promise<RawChunkPayload> {
  const cached = chunkCache.get(chunkId);
  if (cached) return cached;

  const inflight = inflightChunks.get(chunkId);
  if (inflight) return inflight;

  const fileNum = String(chunkId).padStart(3, '0');
  const promise = fetch(`./data/chunks/chunk-${fileNum}.json`)
    .then(async (res) => {
      if (!res.ok) {
        throw new Error(`Failed to load chunk ${fileNum}: HTTP ${res.status}`);
      }
      const payload = (await res.json()) as RawChunkPayload;
      chunkCache.set(chunkId, payload);
      return payload;
    })
    .finally(() => {
      inflightChunks.delete(chunkId);
    });

  inflightChunks.set(chunkId, promise);
  return promise;
}

export async function loadPrompt(id: string): Promise<Prompt> {
  const cached = promptCache.get(id);
  if (cached) return cached;

  const meta = PROMPT_META_BY_ID[id];
  if (!meta) {
    throw new Error(`Unknown prompt id: ${id}`);
  }

  const chunk = await loadChunk(meta.chunk);
  const raw = chunk[id];
  if (!raw) {
    throw new Error(`Prompt ${id} missing from chunk ${meta.chunk}`);
  }
  const parsed = parsePromptJson(meta, raw);
  promptCache.set(id, parsed);
  return parsed;
}

export async function preloadPrompts(ids: string[]): Promise<Prompt[]> {
  return Promise.all(ids.map((id) => loadPrompt(id)));
}
