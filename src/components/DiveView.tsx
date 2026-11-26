/**
 * Owns active dive gameplay phases (countdown, 25s timer, input matching, animated depth plunge, round results).
 * Does not fetch prompt chunks or store completed runs in localStorage directly.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { soundEngine } from '../audio/soundEngine';
import type { DescentVisualState } from '../art/OceanCanvas';
import { TIER_SPRITES } from '../art/pixelSprites';
import { PixelSpriteSvg } from '../art/PixelSpriteSvg';
import { buildPromptIndex, matchPromptAnswer } from '../domain/matcher';
import { calculateTotals } from '../domain/scoring';
import { ACCEPTED_TIER_ORDER, TIERS } from '../domain/tiers';
import type {
  BuddyId,
  DiveMode,
  DiveRunRecord,
  MatchResult,
  Prompt,
  RoundResult,
  TierId,
  UserSettings,
} from '../domain/types';
import { DepthRuler } from './DepthRuler';
import { DiveSummary } from './DiveSummary';

type DivePhase = 'countdown' | 'answering' | 'descending' | 'round_result' | 'summary';

const ROUND_SECONDS = 25;

const DESCENT_DURATION_MS: Record<TierId, number> = {
  miss: 750,
  plankton: 950,
  tooclever: 1350,
  schooler: 1800,
  rare: 2300,
  deepcut: 2700,
  krillion: 3100,
};

interface DiveViewProps {
  mode: DiveMode;
  label: string;
  diveNumber?: number;
  dateEt?: string;
  packId?: string;
  chapterIndex?: number;
  prompts: Prompt[];
  initialRounds?: RoundResult[];
  initialIndex?: number;
  completedRun?: DiveRunRecord;
  settings: UserSettings;
  onProgress?: (rounds: RoundResult[], currentIndex: number) => void;
  onComplete: (run: DiveRunRecord) => BuddyId[];
  onDepthChange: (depth: number) => void;
  onDescentVisualChange?: (state: DescentVisualState | null) => void;
  onPlayAgain?: () => void;
  playAgainLabel?: string;
  onGoHome: () => void;
  onOpenWardrobe: () => void;
}

export function DiveView({
  mode,
  label,
  diveNumber,
  dateEt,
  packId,
  chapterIndex,
  prompts,
  initialRounds = [],
  initialIndex = 0,
  completedRun,
  settings,
  onProgress,
  onComplete,
  onDepthChange,
  onDescentVisualChange,
  onPlayAgain,
  playAgainLabel,
  onGoHome,
  onOpenWardrobe,
}: DiveViewProps) {
  const [phase, setPhase] = useState<DivePhase>(completedRun ? 'summary' : 'countdown');
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [rounds, setRounds] = useState<RoundResult[]>(initialRounds);
  const [finishedRun, setFinishedRun] = useState<DiveRunRecord | null>(completedRun ?? null);
  const [newlyUnlocked, setNewlyUnlocked] = useState<BuddyId[]>([]);

  const [countdownNum, setCountdownNum] = useState(3);
  const [secondsLeft, setSecondsLeft] = useState(ROUND_SECONDS);
  const [inputValue, setInputValue] = useState('');
  const [rejectedText, setRejectedText] = useState<string | null>(null);
  const [pendingCorrection, setPendingCorrection] = useState<MatchResult | null>(null);
  const [latestRound, setLatestRound] = useState<RoundResult | null>(null);

  const [plungeDepth, setPlungeDepth] = useState<number>(() => calculateTotals(initialRounds).totalDepth);
  const [crossedTier, setCrossedTier] = useState<TierId>('miss');
  const plungeRafRef = useRef<number | null>(null);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const activePrompt = prompts[currentIndex];
  const promptIndex = useMemo(
    () => (activePrompt ? buildPromptIndex(activePrompt) : undefined),
    [activePrompt]
  );

  const settledTotals = useMemo(() => {
    if (finishedRun) {
      return { totalScore: finishedRun.totalScore, totalDepth: finishedRun.totalDepth };
    }
    return calculateTotals(rounds);
  }, [finishedRun, rounds]);

  const displayedDepth = phase === 'descending' ? Math.round(plungeDepth) : settledTotals.totalDepth;

  useEffect(() => {
    onDepthChange(displayedDepth);
  }, [displayedDepth, onDepthChange]);

  useEffect(() => {
    return () => {
      if (plungeRafRef.current !== null) {
        window.cancelAnimationFrame(plungeRafRef.current);
      }
      onDescentVisualChange?.(null);
    };
  }, [onDescentVisualChange]);

  // Countdown phase: 3 -> 2 -> 1 -> answering
  useEffect(() => {
    if (phase !== 'countdown') return;
    setCountdownNum(3);
    soundEngine.countdownTick();

    const t1 = window.setTimeout(() => {
      setCountdownNum(2);
      soundEngine.countdownTick();
    }, 750);
    const t2 = window.setTimeout(() => {
      setCountdownNum(1);
      soundEngine.countdownTick();
    }, 1500);
    const t3 = window.setTimeout(() => {
      soundEngine.countdownGo();
      setSecondsLeft(ROUND_SECONDS);
      setInputValue('');
      setRejectedText(null);
      setPendingCorrection(null);
      setPhase('answering');
    }, 2250);

    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
    };
  }, [phase, currentIndex]);

  useEffect(() => {
    if (phase === 'answering') {
      inputRef.current?.focus();
    }
  }, [phase]);

  // 25-second timer loop
  useEffect(() => {
    if (phase !== 'answering') return;

    const timer = window.setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          window.clearInterval(timer);
          finalizeRound({
            promptId: activePrompt.id,
            promptText: activePrompt.text,
            rawAnswer: inputValue.trim(),
            canonicalAnswer: null,
            tier: 'miss',
            points: 0,
            depthMeters: 0,
            timedOut: true,
          });
          return 0;
        }
        if (prev <= 6) {
          soundEngine.urgentTick();
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, currentIndex]);

  const finalizeRound = (result: RoundResult) => {
    const startDepth = calculateTotals(rounds).totalDepth;
    const endDepth = startDepth + result.depthMeters;
    const nextRounds = [...rounds, result];

    setRounds(nextRounds);
    setLatestRound(result);
    setPendingCorrection(null);
    setRejectedText(null);

    if (result.timedOut || result.tier === 'miss') {
      soundEngine.timeout();
    } else {
      soundEngine.acceptTier(result.tier);
    }

    const nextIdx = currentIndex + 1;
    onProgress?.(nextRounds, Math.min(nextIdx, prompts.length - 1));

    setPlungeDepth(startDepth);
    setCrossedTier(result.tier === 'miss' ? 'miss' : 'plankton');
    setPhase('descending');
    onDescentVisualChange?.({
      active: true,
      startDepth,
      targetDepth: endDepth,
      tier: result.tier,
    });

    const duration = settings.lowPowerMode ? 450 : DESCENT_DURATION_MS[result.tier];
    const tStart = performance.now();
    let lastPingIdx = -1;

    const stepPlunge = (now: number) => {
      const t = Math.min(1, (now - tStart) / duration);
      // Cubic ease-out for satisfying plunge deceleration
      const eased = 1 - Math.pow(1 - t, 3);
      const curr = startDepth + (endDepth - startDepth) * eased;
      setPlungeDepth(curr);

      const gained = curr - startDepth;
      let latestTier: TierId = result.tier === 'miss' ? 'miss' : 'plankton';
      for (let i = 0; i < ACCEPTED_TIER_ORDER.length; i++) {
        const tid = ACCEPTED_TIER_ORDER[i];
        if (gained >= TIERS[tid].depthMeters - 1 && TIERS[tid].depthMeters <= result.depthMeters) {
          latestTier = tid;
          if (i > lastPingIdx) {
            lastPingIdx = i;
            if (i > 0) soundEngine.thresholdPing(i);
          }
        }
      }
      setCrossedTier(latestTier);

      if (t < 1) {
        plungeRafRef.current = window.requestAnimationFrame(stepPlunge);
      } else {
        setPlungeDepth(endDepth);
        window.setTimeout(() => {
          onDescentVisualChange?.(null);
          setPhase('round_result');
        }, settings.lowPowerMode ? 120 : 340);
      }
    };

    plungeRafRef.current = window.requestAnimationFrame(stepPlunge);
  };

  const acceptMatch = (match: MatchResult) => {
    finalizeRound({
      promptId: activePrompt.id,
      promptText: activePrompt.text,
      rawAnswer: match.rawInput,
      canonicalAnswer: match.canonical ?? match.rawInput,
      tier: match.tier,
      points: match.points,
      depthMeters: match.depthMeters,
      timedOut: false,
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (phase !== 'answering' || !activePrompt) return;

    const trimmed = inputValue.trim();
    if (!trimmed) return;

    const match = matchPromptAnswer(
      activePrompt,
      trimmed,
      promptIndex,
      settings.answerCorrections
    );

    if (match.kind === 'no_echo') {
      soundEngine.rejectBuzz();
      setRejectedText(`"${trimmed}": no echo. try again`);
      setPendingCorrection(null);
      if (settings.clearRejectedEntries) {
        setInputValue('');
      }
      inputRef.current?.focus();
      return;
    }

    if (match.needsConfirmation) {
      soundEngine.click();
      setRejectedText(null);
      setPendingCorrection(match);
      return;
    }

    acceptMatch(match);
  };

  const handleAdvance = () => {
    soundEngine.click();
    const nextIdx = currentIndex + 1;
    if (nextIdx >= prompts.length) {
      const totals = calculateTotals(rounds);
      const maxScore = prompts.length * 100;
      const runRecord: DiveRunRecord = {
        id: `${mode}-${Date.now()}`,
        mode,
        label,
        diveNumber,
        dateEt,
        packId,
        chapterIndex,
        completedAt: new Date().toISOString(),
        rounds,
        totalScore: totals.totalScore,
        maxScore,
        totalDepth: totals.totalDepth,
      };
      const unlocked = onComplete(runRecord);
      setNewlyUnlocked(unlocked);
      setFinishedRun(runRecord);
      soundEngine.diveComplete();
      setPhase('summary');
      return;
    }

    setCurrentIndex(nextIdx);
    setPhase('countdown');
  };

  useEffect(() => {
    if (phase !== 'round_result') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAdvance();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, currentIndex, rounds]);

  const tierColor = (tier: keyof typeof TIERS) =>
    settings.colorblindMode ? TIERS[tier].colorblindColor : TIERS[tier].color;

  if (phase === 'summary' && finishedRun) {
    return (
      <DiveSummary
        run={finishedRun}
        settings={settings}
        newlyUnlockedBuddies={newlyUnlocked}
        onPlayAgain={onPlayAgain}
        playAgainLabel={playAgainLabel}
        onGoHome={onGoHome}
        onOpenWardrobe={onOpenWardrobe}
      />
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* HUD */}
      <div className="hud-bar">
        <div className="hud-stat">
          <div className="hud-stat-label">DEPTH</div>
          <div className="hud-stat-value" style={{ color: 'var(--cyan)' }}>
            {displayedDepth}m
          </div>
        </div>

        <div className="hud-progress-wrap">
          <div className="hud-segments">
            {prompts.map((p, idx) => {
              const r = rounds[idx];
              const isCurrent = idx === currentIndex && !r;
              const bg = r
                ? tierColor(r.tier)
                : isCurrent
                  ? 'var(--pink)'
                  : 'rgba(11, 22, 43, 0.85)';
              const border = r
                ? tierColor(r.tier)
                : isCurrent
                  ? 'var(--pink)'
                  : '#2b446d';
              return (
                <div
                  key={p.id}
                  className="hud-segment"
                  style={{ background: bg, borderColor: border }}
                />
              );
            })}
          </div>
          <div className="pixel-label" style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
            PROMPT {currentIndex + 1} OF {prompts.length}
          </div>
        </div>

        <div className="hud-stat" style={{ textAlign: 'right' }}>
          <div className="hud-stat-label">SCORE</div>
          <div className="hud-stat-value" style={{ color: 'var(--pink)' }}>
            {settledTotals.totalScore}
          </div>
        </div>
      </div>

      {/* Depth Ruler */}
      <DepthRuler currentDepth={displayedDepth} />

      {/* Center Stage */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          paddingTop: 12,
          paddingRight: 44,
          position: 'relative',
          zIndex: 10,
        }}
      >
        {phase === 'countdown' && (
          <div className="pixel-box" style={{ marginTop: 32, padding: '28px 20px', textAlign: 'center' }}>
            <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
              {label} · PROMPT {currentIndex + 1} OF {prompts.length}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 14 }}>
              descending · the clock starts in
            </div>
            <div className="krillion-title" style={{ fontSize: 56, marginTop: 10 }}>
              {countdownNum}
            </div>
            <button
              type="button"
              className="text-link"
              style={{ marginTop: 14 }}
              onClick={() => {
                soundEngine.countdownGo();
                setSecondsLeft(ROUND_SECONDS);
                setPhase('answering');
              }}
            >
              skip countdown →
            </button>
          </div>
        )}

        {phase === 'answering' && activePrompt && (
          <>
            <div className="pixel-box" style={{ padding: '18px 18px 16px' }}>
              <div className="pixel-label" style={{ fontSize: 11, color: 'var(--pink)', marginBottom: 8 }}>
                PROMPT {currentIndex + 1} OF {prompts.length}
              </div>
              <div
                style={{
                  fontSize: 'clamp(20px, 5vw, 24px)',
                  fontWeight: 700,
                  lineHeight: 1.35,
                  color: '#ffffff',
                }}
              >
                {activePrompt.text}
              </div>
              <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
                ▼ rarer answers sink deeper ▼
              </div>
            </div>

            <div style={{ marginTop: 'auto', paddingBottom: 6 }}>
              {rejectedText && (
                <div
                  role="status"
                  style={{ color: 'var(--amber)', fontSize: 12, marginBottom: 8, textAlign: 'center' }}
                >
                  {rejectedText}
                </div>
              )}

              {pendingCorrection && (
                <div
                  className="pixel-box-cyan"
                  style={{
                    padding: '10px 12px',
                    marginBottom: 10,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                  }}
                >
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Did you mean </span>
                    <strong style={{ color: 'var(--cyan)' }}>"{pendingCorrection.canonical}"</strong>?
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="btn-pixel btn-pink"
                      style={{ padding: '6px 10px', fontSize: 11 }}
                      onClick={() => acceptMatch(pendingCorrection)}
                    >
                      YES
                    </button>
                    <button
                      type="button"
                      className="btn-pixel"
                      style={{ padding: '6px 10px', fontSize: 11 }}
                      onClick={() => {
                        setPendingCorrection(null);
                        inputRef.current?.focus();
                      }}
                    >
                      NO
                    </button>
                  </div>
                </div>
              )}

              <form onSubmit={handleSubmit} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className={`timer-ring ${secondsLeft <= 5 ? 'urgent' : ''}`}>{secondsLeft}</div>

                <div style={{ flex: 1 }}>
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => {
                      setInputValue(e.target.value);
                      if (pendingCorrection) setPendingCorrection(null);
                    }}
                    placeholder="type one answer..."
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    style={{
                      width: '100%',
                      height: 52,
                      padding: '0 12px',
                      background: 'var(--surface-input)',
                      border: '2px solid var(--cyan)',
                      color: '#ffffff',
                      fontSize: 16,
                      outline: 'none',
                    }}
                  />
                  <div style={{ height: 4, background: 'rgba(30, 53, 86, 0.7)', marginTop: 4 }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${(secondsLeft / ROUND_SECONDS) * 100}%`,
                        background: secondsLeft <= 5 ? 'var(--pink)' : 'var(--cyan)',
                        transition: 'width 0.9s linear',
                      }}
                    />
                  </div>
                </div>

                <button type="submit" className="btn-pixel btn-pink" style={{ height: 52, padding: '0 16px' }}>
                  DIVE
                </button>
              </form>
            </div>
          </>
        )}

        {phase === 'descending' && latestRound && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 14,
              pointerEvents: 'none',
            }}
          >
            <div
              key={crossedTier}
              className="tier-crossed-banner"
              style={{ color: tierColor(crossedTier) }}
            >
              <PixelSpriteSvg sprite={TIER_SPRITES[crossedTier]} size={22} />
              <span>
                {TIERS[crossedTier].label} · {TIERS[crossedTier].points} PTS
              </span>
            </div>

            <div className="plunge-pill" style={{ borderColor: tierColor(crossedTier) }}>
              <span>
                {latestRound.canonicalAnswer
                  ? `"${latestRound.canonicalAnswer.toUpperCase()}"`
                  : 'TIME UP'}
              </span>
              <span style={{ color: 'var(--cyan)' }}>▼</span>
            </div>

            <div className="pixel-label" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              SINKING... {displayedDepth}m
            </div>
          </div>
        )}

        {phase === 'round_result' && latestRound && (
          <div
            className="pixel-box-cyan result-card-enter"
            style={{
              marginTop: 28,
              padding: 20,
              textAlign: 'center',
              borderColor: tierColor(latestRound.tier),
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10 }}>
              <PixelSpriteSvg sprite={TIER_SPRITES[latestRound.tier]} size={56} />
            </div>

            <div className="pixel-label" style={{ fontSize: 18, color: tierColor(latestRound.tier) }}>
              {TIERS[latestRound.tier].label}
            </div>

            <div style={{ fontSize: 20, fontWeight: 700, color: '#ffffff', marginTop: 8 }}>
              {latestRound.canonicalAnswer
                ? `"${latestRound.canonicalAnswer}"`
                : latestRound.timedOut
                  ? 'TIME UP!'
                  : 'NO ECHO'}
            </div>

            <div className="pixel-label" style={{ fontSize: 13, color: 'var(--cyan)', marginTop: 8 }}>
              +{latestRound.points} PTS · SINK {latestRound.depthMeters}M
            </div>

            <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10, marginBottom: 18 }}>
              {TIERS[latestRound.tier].flavor}
            </p>

            <button
              type="button"
              className="btn-pixel btn-primary-cyan"
              style={{ width: '100%' }}
              onClick={handleAdvance}
            >
              {currentIndex + 1 >= prompts.length ? 'VIEW DIVE SUMMARY ▼' : 'DESCEND ▼'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
