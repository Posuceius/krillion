/**
 * Owns SQLite-backed answer matching (exact, alias, affix, Roman/abbrev, surname, and indexed fuzzy) plus tier browsing.
 * Does not manage round timers, persistence, or React UI state.
 */
import {
  fuzzyLookupKeys,
  generateQueryCandidates,
  levenshtein,
  normalizeAnswer,
  stripLeadingArticle,
} from '../domain/matcher';
import { ACCEPTED_TIER_ORDER, TIERS } from '../domain/tiers';
import type { AcceptedTierId, MatchResult, PromptMeta } from '../domain/types';
import { PROMPT_MANIFEST } from './manifest';
import { runQuery, warmupDatabase, type SqlRow } from './sqliteDb';

export { warmupDatabase };

export const PROMPT_META_BY_ID: Record<string, PromptMeta> = Object.fromEntries(
  PROMPT_MANIFEST.map((m) => [m.id, m])
);

const TIER_BY_IDX: AcceptedTierId[] = [
  'plankton',
  'tooclever',
  'schooler',
  'rare',
  'deepcut',
  'krillion',
];

const TIER_IDX_BY_ID: Record<AcceptedTierId, number> = {
  plankton: 0,
  tooclever: 1,
  schooler: 2,
  rare: 3,
  deepcut: 4,
  krillion: 5,
};

interface MatchRow extends SqlRow {
  canonical: string;
  tier: number;
  form_kind: number;
}

interface FuzzyRow extends SqlRow {
  canonical: string;
  tier: number;
  matched_norm?: string | null;
}

interface TierSampleRow extends SqlRow {
  tier: number;
  canonical: string;
}

interface TierCountRow extends SqlRow {
  tier: number;
  cnt: number;
}

export async function matchPromptAnswerRemote(
  meta: PromptMeta,
  rawInput: string,
  answerCorrectionsEnabled = true
): Promise<MatchResult> {
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

  const candidates = generateQueryCandidates(rawInput, meta.formLevel);
  if (candidates.length > 0) {
    const placeholders = candidates.map(() => '?').join(', ');
    const rows = await runQuery<MatchRow>(
      `SELECT e.canonical, pa.tier, ef.form_kind
       FROM entity_forms ef
       JOIN prompt_answers pa ON pa.entity_id = ef.entity_id
       JOIN entities e ON e.id = pa.entity_id
       WHERE pa.prompt_id = ?
         AND ef.norm IN (${placeholders})
         AND ef.form_kind <= ?
       ORDER BY (CASE WHEN ef.form_kind = 0 THEN 0 ELSE 1 END) ASC, pa.rank ASC, ef.form_kind ASC
       LIMIT 1`,
      [meta.dbId, ...candidates, meta.formLevel]
    );

    if (rows.length > 0) {
      const hit = rows[0];
      const tierId = TIER_BY_IDX[Number(hit.tier)] ?? 'plankton';
      const tierDef = TIERS[tierId];
      const canonical = String(hit.canonical);
      const isExact =
        Number(hit.form_kind) === 0 && normalizeAnswer(canonical) === norm;
      return {
        kind: isExact ? 'exact' : 'alias',
        rawInput,
        canonical,
        tier: tierId,
        points: tierDef.points,
        depthMeters: tierDef.depthMeters,
        needsConfirmation: false,
      };
    }
  }

  // Indexed fuzzy typo check on top 6,000 ranked canonicals using p3 + s3 partial indexes
  const stripped = stripLeadingArticle(norm);
  if (stripped.length >= 4) {
    const maxDist = stripped.length >= 7 ? 2 : 1;
    const { p3Keys, s3Key } = fuzzyLookupKeys(stripped);

    const candidateRows: FuzzyRow[] = [];
    if (p3Keys.length > 0) {
      const p3Placeholders = p3Keys.map(() => '?').join(', ');
      const p3Hits = await runQuery<FuzzyRow>(
        `SELECT DISTINCT e.canonical, pa.tier, pa.rank
         FROM prompt_answers pa
         JOIN entities e ON e.id = pa.entity_id
         WHERE pa.prompt_id = ?
           AND pa.rank < 3000
           AND pa.p3 IN (${p3Placeholders})
         ORDER BY pa.rank ASC
         LIMIT 250`,
        [meta.dbId, ...p3Keys]
      );
      candidateRows.push(...p3Hits);
    }

    let bestDist = maxDist + 1;
    let bestHit: FuzzyRow | null = null;
    let tied = false;

    const evaluate = (rows: FuzzyRow[]) => {
      for (const row of rows) {
        const targetNorm = row.matched_norm
          ? String(row.matched_norm)
          : stripLeadingArticle(normalizeAnswer(String(row.canonical)));
        if (!targetNorm) continue;
        const dist = levenshtein(stripped, targetNorm, maxDist);
        if (dist <= maxDist) {
          if (dist < bestDist) {
            bestDist = dist;
            bestHit = row;
            tied = false;
          } else if (
            dist === bestDist &&
            bestHit &&
            bestHit.canonical !== row.canonical
          ) {
            tied = true;
          }
        }
      }
    };

    evaluate(candidateRows);

    if (!bestHit && meta.formLevel >= 1 && p3Keys.length > 0) {
      const prefix3 = p3Keys[0];
      const formHits = await runQuery<FuzzyRow>(
        `SELECT e.canonical, pa.tier, ef.norm AS matched_norm
         FROM entity_forms ef
         JOIN prompt_answers pa ON pa.entity_id = ef.entity_id
         JOIN entities e ON e.id = pa.entity_id
         WHERE ef.norm >= ? AND ef.norm < ?
           AND ef.form_kind <= ?
           AND pa.prompt_id = ?
           AND pa.rank < 3000
         ORDER BY ef.form_kind ASC, pa.rank ASC
         LIMIT 200`,
        [prefix3, `${prefix3}\uffff`, meta.formLevel, meta.dbId]
      );
      evaluate(formHits);
    }

    if (!bestHit && s3Key) {
      const s3Hits = await runQuery<FuzzyRow>(
        `SELECT e.canonical, pa.tier, pa.rank
         FROM prompt_answers pa
         JOIN entities e ON e.id = pa.entity_id
         WHERE pa.prompt_id = ?
           AND pa.rank < 3000
           AND pa.s3 = ?
         ORDER BY pa.rank ASC
         LIMIT 150`,
        [meta.dbId, s3Key]
      );
      evaluate(s3Hits);
    }

    if (bestHit && (!tied || bestDist === 1)) {
      const chosen = bestHit as FuzzyRow;
      const tierId = TIER_BY_IDX[Number(chosen.tier)] ?? 'plankton';
      const tierDef = TIERS[tierId];
      return {
        kind: 'fuzzy',
        rawInput,
        canonical: String(chosen.canonical),
        tier: tierId,
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

export async function loadPromptTierSamples(
  meta: PromptMeta,
  limitPerTier = 12
): Promise<Record<AcceptedTierId, { total: number; items: string[] }>> {
  const counts = await runQuery<TierCountRow>(
    `SELECT tier, COUNT(*) AS cnt FROM prompt_answers WHERE prompt_id = ? GROUP BY tier`,
    [meta.dbId]
  );

  const out = {} as Record<AcceptedTierId, { total: number; items: string[] }>;
  for (const tid of ACCEPTED_TIER_ORDER) {
    out[tid] = { total: 0, items: [] };
  }
  for (const row of counts) {
    const tid = TIER_BY_IDX[Number(row.tier)];
    if (tid) out[tid].total = Number(row.cnt);
  }

  await Promise.all(
    ACCEPTED_TIER_ORDER.map(async (tid) => {
      if (out[tid].total === 0) return;
      const tIdx = TIER_IDX_BY_ID[tid];
      const rows = await runQuery<TierSampleRow>(
        `SELECT e.canonical, pa.tier
         FROM prompt_answers pa
         JOIN entities e ON e.id = pa.entity_id
         WHERE pa.prompt_id = ? AND pa.tier = ?
         ORDER BY pa.rank ASC
         LIMIT ?`,
        [meta.dbId, tIdx, limitPerTier]
      );
      out[tid].items = rows.map((r) => String(r.canonical));
    })
  );

  return out;
}

export async function searchPromptAnswers(
  meta: PromptMeta,
  rawQuery: string,
  limit = 60
): Promise<Array<{ canonical: string; tier: AcceptedTierId }>> {
  const norm = normalizeAnswer(rawQuery);
  if (!norm) return [];

  const rows = await runQuery<FuzzyRow>(
    `SELECT e.canonical, pa.tier
     FROM entity_forms ef
     JOIN prompt_answers pa ON pa.entity_id = ef.entity_id
     JOIN entities e ON e.id = pa.entity_id
     WHERE pa.prompt_id = ?
       AND ef.form_kind <= ?
       AND ef.norm >= ?
       AND ef.norm < ?
     GROUP BY pa.entity_id
     ORDER BY MIN(pa.rank) ASC
     LIMIT ?`,
    [meta.dbId, meta.formLevel, norm, `${norm}\uffff`, limit]
  );

  return rows.map((r) => ({
    canonical: String(r.canonical),
    tier: TIER_BY_IDX[Number(r.tier)] ?? 'plankton',
  }));
}
