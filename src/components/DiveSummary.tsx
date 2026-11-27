/**
 * Owns end-of-dive summary cards, clipboard sharing, SQLite tier browsing, and live answer search.
 * Does not run active round timers or persist logbook history.
 */
import { useEffect, useState } from 'react';
import { BUDDY_SPRITES, TIER_SPRITES } from '../art/pixelSprites';
import { PixelSpriteSvg } from '../art/PixelSpriteSvg';
import {
  PROMPT_META_BY_ID,
  loadPromptTierSamples,
  matchPromptAnswerRemote,
  searchPromptAnswers,
} from '../data';
import { formatShareCard } from '../domain/scoring';
import { ACCEPTED_TIER_ORDER, BUDDIES, TIERS, getOceanZone } from '../domain/tiers';
import type {
  AcceptedTierId,
  BuddyId,
  DiveRunRecord,
  MatchResult,
  UserSettings,
} from '../domain/types';

interface DiveSummaryProps {
  run: DiveRunRecord;
  settings: UserSettings;
  newlyUnlockedBuddies: BuddyId[];
  onPlayAgain?: () => void;
  playAgainLabel?: string;
  onGoHome: () => void;
  onOpenWardrobe: () => void;
}

type TierSamplesMap = Record<AcceptedTierId, { total: number; items: string[] }>;

const DEFAULT_TIER_PREVIEW = 12;
const EXPANDED_TIER_PREVIEW = 120;

export function DiveSummary({
  run,
  settings,
  newlyUnlockedBuddies,
  onPlayAgain,
  playAgainLabel = 'DIVE AGAIN ∞',
  onGoHome,
  onOpenWardrobe,
}: DiveSummaryProps) {
  const [copied, setCopied] = useState(false);
  const [expandedPromptId, setExpandedPromptId] = useState<string | null>(null);
  const [tierSamples, setTierSamples] = useState<Record<string, TierSamplesMap>>({});
  const [loadingPromptId, setLoadingPromptId] = useState<string | null>(null);
  const [answerQuery, setAnswerQuery] = useState('');
  const [queryMatch, setQueryMatch] = useState<MatchResult | null>(null);
  const [searchHits, setSearchHits] = useState<Array<{ canonical: string; tier: AcceptedTierId }>>([]);
  const [showAllTiers, setShowAllTiers] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!expandedPromptId) return;
    setAnswerQuery('');
    setQueryMatch(null);
    setSearchHits([]);
    setShowAllTiers({});

    if (tierSamples[expandedPromptId]) return;
    const meta = PROMPT_META_BY_ID[expandedPromptId];
    if (!meta) return;

    let cancelled = false;
    setLoadingPromptId(expandedPromptId);
    void loadPromptTierSamples(meta, DEFAULT_TIER_PREVIEW)
      .then((samples) => {
        if (!cancelled) {
          setTierSamples((prev) => ({ ...prev, [expandedPromptId]: samples }));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPromptId((curr) => (curr === expandedPromptId ? null : curr));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [expandedPromptId, tierSamples]);

  useEffect(() => {
    const trimmed = answerQuery.trim();
    if (!expandedPromptId || !trimmed) {
      setQueryMatch(null);
      setSearchHits([]);
      return;
    }
    const meta = PROMPT_META_BY_ID[expandedPromptId];
    if (!meta) return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void Promise.all([
        matchPromptAnswerRemote(meta, trimmed, true),
        searchPromptAnswers(meta, trimmed, 60),
      ]).then(([matchRes, hits]) => {
        if (!cancelled) {
          setQueryMatch(matchRes);
          setSearchHits(hits);
        }
      });
    }, 150);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [expandedPromptId, answerQuery]);

  const handleShowMoreTier = (promptId: string, tierId: AcceptedTierId) => {
    setShowAllTiers((prev) => ({ ...prev, [tierId]: true }));
    const meta = PROMPT_META_BY_ID[promptId];
    const current = tierSamples[promptId];
    if (!meta || (current && current[tierId].items.length > DEFAULT_TIER_PREVIEW)) return;

    void loadPromptTierSamples(meta, EXPANDED_TIER_PREVIEW).then((expanded) => {
      setTierSamples((prev) => ({ ...prev, [promptId]: expanded }));
    });
  };

  const zone = getOceanZone(run.totalDepth);
  const tierColor = (tier: keyof typeof TIERS) =>
    settings.colorblindMode ? TIERS[tier].colorblindColor : TIERS[tier].color;

  const handleCopy = async () => {
    const url = settings.shareLink
      ? `${window.location.origin}${window.location.pathname}`
      : undefined;
    const text = formatShareCard(run, url);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 24 }}>
      <div className="pixel-box-cyan" style={{ padding: 18, textAlign: 'center' }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          {run.label} · COMPLETE
        </div>
        <div className="pixel-label" style={{ fontSize: 34, marginTop: 6, color: '#ffffff' }}>
          {run.totalDepth.toLocaleString()}m
        </div>
        <div
          className="pixel-label"
          style={{
            display: 'inline-block',
            marginTop: 6,
            padding: '4px 10px',
            border: `1px solid ${zone.badgeColor}`,
            color: zone.badgeColor,
            fontSize: 11,
          }}
        >
          {zone.name} · {run.totalScore}/{run.maxScore} PTS
        </div>

        <div style={{ marginTop: 12, fontSize: 20, letterSpacing: 4 }} aria-label="Tier summary emojis">
          {run.rounds.map((r, i) => (
            <span key={i} title={TIERS[r.tier].label}>
              {TIERS[r.tier].emoji}
            </span>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button type="button" className="btn-pixel btn-pink" style={{ flex: 1 }} onClick={handleCopy}>
            {copied ? 'COPIED TO CLIPBOARD!' : 'COPY RESULT'}
          </button>
          {onPlayAgain && (
            <button type="button" className="btn-pixel" style={{ flex: 1 }} onClick={onPlayAgain}>
              {playAgainLabel}
            </button>
          )}
        </div>
      </div>

      {newlyUnlockedBuddies.length > 0 && (
        <div
          className="pixel-box"
          style={{
            padding: 14,
            borderColor: 'var(--gold)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <PixelSpriteSvg sprite={BUDDY_SPRITES[newlyUnlockedBuddies[0]]} size={40} />
            <div>
              <div className="pixel-label" style={{ fontSize: 11, color: 'var(--gold)' }}>
                NEW DIVE BUDDY UNLOCKED!
              </div>
              <div style={{ fontSize: 12, marginTop: 2 }}>{BUDDIES[newlyUnlockedBuddies[0]].name}</div>
            </div>
          </div>
          <button type="button" className="btn-pixel" onClick={onOpenWardrobe}>
            EQUIP
          </button>
        </div>
      )}

      <div className="divider-line">DIVE BREAKDOWN</div>

      {run.rounds.map((round, idx) => {
        const isOpen = expandedPromptId === round.promptId;
        const meta = PROMPT_META_BY_ID[round.promptId];
        const samples = tierSamples[round.promptId];
        const color = tierColor(round.tier);
        const hasSearch = Boolean(answerQuery.trim());

        return (
          <div key={`${round.promptId}-${idx}`} className="pixel-box" style={{ padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  PROMPT {idx + 1}: {round.promptText}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                  <PixelSpriteSvg sprite={TIER_SPRITES[round.tier]} size={24} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#ffffff' }}>
                    {round.canonicalAnswer ?? (round.timedOut ? '(Time out)' : '(No echo)')}
                  </span>
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div className="pixel-label" style={{ fontSize: 10, color }}>
                  {TIERS[round.tier].shortLabel}
                </div>
                <div className="pixel-label" style={{ fontSize: 13, marginTop: 2 }}>
                  +{round.points} ({round.depthMeters}m)
                </div>
              </div>
            </div>

            {meta && (
              <div style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="text-link"
                  style={{ fontSize: 11 }}
                  onClick={() => setExpandedPromptId(isOpen ? null : round.promptId)}
                >
                  {isOpen
                    ? 'Hide accepted answers ▲'
                    : `Explore ${meta.answerCount.toLocaleString()} accepted answers ▼`}
                </button>

                {isOpen && (
                  <div
                    style={{
                      marginTop: 8,
                      paddingTop: 8,
                      borderTop: '1px dashed var(--border-dim)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                      fontSize: 11,
                    }}
                  >
                    {loadingPromptId === round.promptId && !samples ? (
                      <div style={{ color: 'var(--text-muted)' }}>Querying SQLite answer pool...</div>
                    ) : samples ? (
                      <>
                        <input
                          type="text"
                          value={answerQuery}
                          onChange={(e) => setAnswerQuery(e.target.value)}
                          placeholder="Check any answer (type to see its tier)..."
                          style={{
                            width: '100%',
                            padding: '7px 10px',
                            background: 'var(--surface-input)',
                            border: '1px solid var(--border-bright)',
                            color: '#ffffff',
                            fontSize: 12,
                          }}
                        />

                        {queryMatch && (
                          <div
                            style={{
                              padding: '6px 8px',
                              background: 'rgba(8, 16, 33, 0.85)',
                              border: `1px solid ${tierColor(queryMatch.tier)}`,
                            }}
                          >
                            {queryMatch.kind === 'no_echo' ? (
                              <span style={{ color: 'var(--amber)' }}>
                                "{answerQuery.trim()}" - no exact match in pool
                              </span>
                            ) : (
                              <span>
                                <strong style={{ color: '#ffffff' }}>{queryMatch.canonical}</strong>
                                {' -> '}
                                <span
                                  className="pixel-label"
                                  style={{ color: tierColor(queryMatch.tier), fontSize: 10 }}
                                >
                                  {TIERS[queryMatch.tier].label} (+{queryMatch.points} pts / {queryMatch.depthMeters}m)
                                </span>
                                {queryMatch.kind === 'fuzzy' ? ' (close typo match)' : ''}
                              </span>
                            )}
                          </div>
                        )}

                        {hasSearch && searchHits.length > 0 && (
                          <div style={{ lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                            <span className="pixel-label" style={{ fontSize: 10, color: 'var(--cyan)', marginRight: 6 }}>
                              MATCHING ANSWERS ({searchHits.length}):
                            </span>
                            {searchHits.map((h) => `${h.canonical} [${TIERS[h.tier].shortLabel}]`).join(', ')}
                          </div>
                        )}

                        {!hasSearch &&
                          [...ACCEPTED_TIER_ORDER].reverse().map((tId) => {
                            const tierData = samples[tId];
                            if (!tierData || tierData.total === 0) return null;

                            const showAll = Boolean(showAllTiers[tId]);
                            const visible = showAll
                              ? tierData.items.slice(0, EXPANDED_TIER_PREVIEW)
                              : tierData.items.slice(0, DEFAULT_TIER_PREVIEW);
                            const remaining = tierData.total - visible.length;

                            return (
                              <div key={tId} style={{ lineHeight: 1.5 }}>
                                <span
                                  className="pixel-label"
                                  style={{ color: tierColor(tId), fontSize: 10, marginRight: 6 }}
                                >
                                  {TIERS[tId].shortLabel} ({TIERS[tId].points}) [{tierData.total.toLocaleString()}]:
                                </span>
                                <span style={{ color: 'var(--text-secondary)' }}>
                                  {visible.join(', ')}
                                </span>
                                {remaining > 0 && !showAll && (
                                  <button
                                    type="button"
                                    className="text-link"
                                    style={{ marginLeft: 6, fontSize: 10 }}
                                    onClick={() => handleShowMoreTier(round.promptId, tId)}
                                  >
                                    Show more ({remaining.toLocaleString()} more)
                                  </button>
                                )}
                                {showAll && remaining > 0 && (
                                  <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                                    (+{remaining.toLocaleString()} more - use search box above)
                                  </span>
                                )}
                              </div>
                            );
                          })}
                      </>
                    ) : null}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      <button type="button" className="btn-pixel" onClick={onGoHome}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
