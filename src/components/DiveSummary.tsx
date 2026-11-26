/**
 * Owns end-of-dive summary cards, clipboard sharing, lazy tier answer exploration, and answer search.
 * Does not run active round timers or persist logbook history.
 */
import { useEffect, useMemo, useState } from 'react';
import { BUDDY_SPRITES, TIER_SPRITES } from '../art/pixelSprites';
import { PixelSpriteSvg } from '../art/PixelSpriteSvg';
import { PROMPT_META_BY_ID, getCachedPrompt, loadPrompt } from '../data';
import { buildPromptIndex, matchPromptAnswer, normalizeAnswer } from '../domain/matcher';
import { formatShareCard } from '../domain/scoring';
import { ACCEPTED_TIER_ORDER, BUDDIES, TIERS, getOceanZone } from '../domain/tiers';
import type { BuddyId, DiveRunRecord, Prompt, UserSettings } from '../domain/types';

interface DiveSummaryProps {
  run: DiveRunRecord;
  settings: UserSettings;
  newlyUnlockedBuddies: BuddyId[];
  onPlayAgain?: () => void;
  playAgainLabel?: string;
  onGoHome: () => void;
  onOpenWardrobe: () => void;
}

const DEFAULT_TIER_PREVIEW = 12;

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
  const [loadedPrompts, setLoadedPrompts] = useState<Record<string, Prompt>>({});
  const [loadingPromptId, setLoadingPromptId] = useState<string | null>(null);
  const [answerQuery, setAnswerQuery] = useState('');
  const [showAllTiers, setShowAllTiers] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!expandedPromptId) return;
    setAnswerQuery('');
    setShowAllTiers({});

    if (loadedPrompts[expandedPromptId]) return;
    const cached = getCachedPrompt(expandedPromptId);
    if (cached) {
      setLoadedPrompts((prev) => ({ ...prev, [expandedPromptId]: cached }));
      return;
    }

    setLoadingPromptId(expandedPromptId);
    void loadPrompt(expandedPromptId)
      .then((prompt) => {
        setLoadedPrompts((prev) => ({ ...prev, [expandedPromptId]: prompt }));
      })
      .finally(() => {
        setLoadingPromptId((curr) => (curr === expandedPromptId ? null : curr));
      });
  }, [expandedPromptId, loadedPrompts]);

  const activeExpandedPrompt = expandedPromptId ? loadedPrompts[expandedPromptId] : undefined;
  const activePromptIndex = useMemo(
    () => (activeExpandedPrompt ? buildPromptIndex(activeExpandedPrompt) : undefined),
    [activeExpandedPrompt]
  );

  const queryMatch = useMemo(() => {
    if (!activeExpandedPrompt || !answerQuery.trim()) return null;
    return matchPromptAnswer(activeExpandedPrompt, answerQuery.trim(), activePromptIndex, true);
  }, [activeExpandedPrompt, activePromptIndex, answerQuery]);

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
        const prompt = loadedPrompts[round.promptId];
        const color = tierColor(round.tier);
        const normQuery = normalizeAnswer(answerQuery);

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
                    {loadingPromptId === round.promptId && !prompt ? (
                      <div style={{ color: 'var(--text-muted)' }}>Loading answer pool...</div>
                    ) : prompt ? (
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

                        {[...ACCEPTED_TIER_ORDER].reverse().map((tId) => {
                          const allInTier = prompt.answers
                            .filter((a) => a.tier === tId)
                            .map((a) => a.canonical);
                          const filtered = normQuery
                            ? allInTier.filter((c) => normalizeAnswer(c).includes(normQuery))
                            : allInTier;
                          if (filtered.length === 0) return null;

                          const showAll = Boolean(showAllTiers[tId]) || Boolean(normQuery);
                          const visible = showAll
                            ? filtered.slice(0, 120)
                            : filtered.slice(0, DEFAULT_TIER_PREVIEW);
                          const remaining = filtered.length - visible.length;

                          return (
                            <div key={tId} style={{ lineHeight: 1.5 }}>
                              <span
                                className="pixel-label"
                                style={{ color: tierColor(tId), fontSize: 10, marginRight: 6 }}
                              >
                                {TIERS[tId].shortLabel} ({TIERS[tId].points}) [{allInTier.length}]:
                              </span>
                              <span style={{ color: 'var(--text-secondary)' }}>
                                {visible.join(', ')}
                              </span>
                              {remaining > 0 && !normQuery && (
                                <button
                                  type="button"
                                  className="text-link"
                                  style={{ marginLeft: 6, fontSize: 10 }}
                                  onClick={() =>
                                    setShowAllTiers((prev) => ({ ...prev, [tId]: true }))
                                  }
                                >
                                  Show more ({remaining} more)
                                </button>
                              )}
                              {normQuery && filtered.length > 120 && (
                                <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                                  (+{filtered.length - 120} more matches)
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
