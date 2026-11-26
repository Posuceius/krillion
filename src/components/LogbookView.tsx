/**
 * Owns the My Krillion stats view (streaks, tier distribution, earned buddies, recent dives, reset).
 * Does not compute streak rules or edit localStorage directly (delegates via onResetAll).
 */
import { useState } from 'react';
import { BUDDY_SPRITES } from '../art/pixelSprites';
import { PixelSpriteSvg } from '../art/PixelSpriteSvg';
import { getUnlockedBuddies } from '../domain/scoring';
import { BUDDIES, TIERS, TIER_ORDER } from '../domain/tiers';
import type { LogbookState, UserSettings } from '../domain/types';

interface LogbookViewProps {
  logbook: LogbookState;
  settings: UserSettings;
  onResetAll: () => void;
  onOpenWardrobe: () => void;
  onBack: () => void;
}

export function LogbookView({
  logbook,
  settings,
  onResetAll,
  onOpenWardrobe,
  onBack,
}: LogbookViewProps) {
  const [confirmReset, setConfirmReset] = useState(false);

  const dailyRuns = Object.values(logbook.dailyCompleted);
  const allRuns = [
    ...dailyRuns,
    ...Object.values(logbook.archiveCompleted),
    ...Object.values(logbook.packCompleted),
    ...logbook.unlimitedRuns,
  ].sort((a, b) => b.completedAt.localeCompare(a.completedAt));

  const bestDailyScore = dailyRuns.reduce((m, r) => Math.max(m, r.totalScore), 0);
  const deepestDive = allRuns.reduce((m, r) => Math.max(m, r.totalDepth), 0);
  const unlockedBuddies = getUnlockedBuddies(logbook.bestStreak);

  const maxTierCount = Math.max(
    1,
    ...TIER_ORDER.map((t) => logbook.tierCounts[t] ?? 0)
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 24 }}>
      <div className="pixel-box" style={{ padding: 16 }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          DIVER'S LOGBOOK · LOCAL STORAGE
        </div>
        <h2 className="krillion-title" style={{ fontSize: 24, marginTop: 4 }}>
          MY KRILLION
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 10,
            marginTop: 14,
          }}
        >
          <div className="hud-stat">
            <div className="hud-stat-label">CURRENT STREAK</div>
            <div className="hud-stat-value" style={{ color: 'var(--cyan)' }}>
              {logbook.currentStreak}d
            </div>
          </div>
          <div className="hud-stat">
            <div className="hud-stat-label">BEST STREAK</div>
            <div className="hud-stat-value" style={{ color: 'var(--gold)' }}>
              {logbook.bestStreak}d
            </div>
          </div>
          <div className="hud-stat">
            <div className="hud-stat-label">DAILY DIVES</div>
            <div className="hud-stat-value">{dailyRuns.length}</div>
          </div>
          <div className="hud-stat">
            <div className="hud-stat-label">BEST DAILY SCORE</div>
            <div className="hud-stat-value" style={{ color: 'var(--pink)' }}>
              {bestDailyScore}/700
            </div>
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 12 }}>
          Deepest single run: <strong style={{ color: '#ffffff' }}>{deepestDive.toLocaleString()}m</strong>
        </div>
      </div>

      <div className="pixel-box" style={{ padding: 16 }}>
        <div className="pixel-label" style={{ fontSize: 12, marginBottom: 10 }}>
          TIER DISTRIBUTION
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[...TIER_ORDER].reverse().map((tierId) => {
            const count = logbook.tierCounts[tierId] ?? 0;
            const color = settings.colorblindMode
              ? TIERS[tierId].colorblindColor
              : TIERS[tierId].color;
            return (
              <div key={tierId} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                <span style={{ width: 92, color }} className="pixel-label">
                  {TIERS[tierId].shortLabel}
                </span>
                <div style={{ flex: 1, height: 12, background: '#071122', border: '1px solid var(--border-dim)' }}>
                  <div
                    style={{
                      width: `${(count / maxTierCount) * 100}%`,
                      height: '100%',
                      background: color,
                    }}
                  />
                </div>
                <span style={{ width: 28, textAlign: 'right' }}>{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="pixel-box" style={{ padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="pixel-label" style={{ fontSize: 12 }}>
            EARNED DIVE BUDDIES ({unlockedBuddies.length}/9)
          </div>
          <button type="button" className="text-link" onClick={onOpenWardrobe}>
            Open Wardrobe
          </button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
          {unlockedBuddies.map((bId) => (
            <div key={bId} title={BUDDIES[bId].name} style={{ textAlign: 'center' }}>
              <PixelSpriteSvg sprite={BUDDY_SPRITES[bId]} size={34} />
            </div>
          ))}
        </div>
      </div>

      {allRuns.length > 0 && (
        <div className="pixel-box" style={{ padding: 16 }}>
          <div className="pixel-label" style={{ fontSize: 12, marginBottom: 10 }}>
            RECENT DIVES
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {allRuns.slice(0, 8).map((run) => (
              <div
                key={run.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 12,
                  borderBottom: '1px solid rgba(30,53,86,0.45)',
                  paddingBottom: 6,
                }}
              >
                <span>{run.label}</span>
                <span style={{ color: 'var(--cyan)' }}>
                  {run.totalDepth.toLocaleString()}m ({run.totalScore}/{run.maxScore})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="pixel-box" style={{ padding: 14 }}>
        {!confirmReset ? (
          <button
            type="button"
            className="btn-pixel"
            style={{ width: '100%', borderColor: '#7f1d1d', color: '#fca5a5' }}
            onClick={() => setConfirmReset(true)}
          >
            RESET LOCAL LOGBOOK DATA
          </button>
        ) : (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#fca5a5', marginBottom: 10 }}>
              Erase all local streaks, scores, and buddy unlocks on this browser?
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn-pixel btn-pink"
                style={{ flex: 1 }}
                onClick={() => {
                  onResetAll();
                  setConfirmReset(false);
                }}
              >
                CONFIRM RESET
              </button>
              <button
                type="button"
                className="btn-pixel"
                style={{ flex: 1 }}
                onClick={() => setConfirmReset(false)}
              >
                CANCEL
              </button>
            </div>
          </div>
        )}
      </div>

      <button type="button" className="btn-pixel" onClick={onBack}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
