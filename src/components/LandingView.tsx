/**
 * Owns the surface landing screen, daily countdown, expandable How to Play, and mode launch buttons.
 * Does not load prompt chunks or render global navigation modals.
 */
import { useEffect, useState } from 'react';
import { formatCountdown, getMsUntilNextEasternMidnight } from '../domain/dailySchedule';
import type { DiveRunRecord, InProgressDive } from '../domain/types';

interface LandingViewProps {
  diveNumber: number;
  promptCount: number;
  totalAnswers: number;
  completedToday: DiveRunRecord | undefined;
  inProgressDaily: InProgressDive | null;
  currentStreak: number;
  onStartDaily: () => void;
  onOpenArchive: () => void;
  onOpenPacks: () => void;
  onOpenUnlimited: () => void;
}

export function LandingView({
  diveNumber,
  promptCount,
  totalAnswers,
  completedToday,
  inProgressDaily,
  currentStreak,
  onStartDaily,
  onOpenArchive,
  onOpenPacks,
  onOpenUnlimited,
}: LandingViewProps) {
  const [howToOpen, setHowToOpen] = useState(false);
  const [countdown, setCountdown] = useState(() =>
    formatCountdown(getMsUntilNextEasternMidnight())
  );

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCountdown(formatCountdown(getMsUntilNextEasternMidnight()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <main
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        paddingTop: 24,
      }}
    >
      {/* Hero section positioned above the ocean horizon */}
      <div style={{ textAlign: 'center', marginTop: 12 }}>
        <h1 className="krillion-title" style={{ fontSize: 'clamp(36px, 10vw, 48px)' }}>
          KRILLION
        </h1>
        <div
          className="pixel-label"
          style={{
            fontSize: 13,
            color: '#1b5080',
            letterSpacing: '0.28em',
            marginTop: 4,
            fontWeight: 700,
          }}
        >
          THE DAILY DIVE
        </div>
        <p
          style={{
            fontSize: 12,
            color: '#153b60',
            margin: '12px auto 0',
            maxWidth: 360,
            lineHeight: 1.5,
            fontWeight: 500,
          }}
        >
          7 prompts · {promptCount.toLocaleString()} prompts · {totalAnswers.toLocaleString()} answers
        </p>
      </div>

      {/* Lower ocean action area */}
      <div style={{ marginTop: 'auto', paddingTop: 140 }}>
        <div style={{ marginBottom: 14 }}>
          <button
            type="button"
            onClick={() => setHowToOpen((v) => !v)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-display)',
              fontSize: 11,
              letterSpacing: '0.12em',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 0',
            }}
          >
            <span>{howToOpen ? '▼' : '▶'}</span>
            <span>HOW TO PLAY</span>
          </button>

          {howToOpen && (
            <div
              className="pixel-box"
              style={{
                marginTop: 8,
                padding: '12px 14px',
                fontSize: 12,
                lineHeight: 1.6,
                color: 'var(--text-secondary)',
              }}
            >
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                <li>Every day has 7 prompts. Same prompts for everyone worldwide.</li>
                <li>You have 25 seconds to type one valid answer per prompt.</li>
                <li>Obvious answers stay near the surface (Plankton = 5 pts / 50m).</li>
                <li>Obscure gems sink up to 100 pts (1,000m) for One in a Krillion!</li>
                <li>Reach 7,000m total depth to hit the Hadal Trench floor.</li>
                <li>Keep your daily streak alive to unlock all 9 Dive Buddies.</li>
              </ul>
            </div>
          )}
        </div>

        <button
          type="button"
          className="btn-pixel btn-primary-cyan"
          style={{ width: '100%' }}
          onClick={onStartDaily}
        >
          {completedToday
            ? '▼ VIEW TODAY\'S DIVE ▼'
            : inProgressDaily
              ? `▼ RESUME DIVE (${inProgressDaily.currentIndex + 1}/7) ▼`
              : '▼ BEGIN DESCENT ▼'}
        </button>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 10,
            fontSize: 11,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-display)',
          }}
        >
          <span>DIVE #{diveNumber}</span>
          <span>
            {completedToday
              ? `NEXT DIVE IN ${countdown}`
              : currentStreak > 0
                ? `STREAK: ${currentStreak}D`
                : 'NEW DIVE DAILY AT 00:00 ET'}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8,
            marginTop: 14,
          }}
        >
          <button
            type="button"
            className="btn-pixel"
            style={{ fontSize: 11, padding: '10px 6px' }}
            onClick={onOpenArchive}
          >
            ARCHIVE ⟲
          </button>
          <button
            type="button"
            className="btn-pixel"
            style={{ fontSize: 11, padding: '10px 6px' }}
            onClick={onOpenPacks}
          >
            THEMED PACKS
          </button>
          <button
            type="button"
            className="btn-pixel"
            style={{ fontSize: 11, padding: '10px 6px' }}
            onClick={onOpenUnlimited}
          >
            UNLIMITED ∞
          </button>
        </div>
      </div>
    </main>
  );
}
