/**
 * Owns the Archive dive browser and filterable list of past Daily Dives (#1 through yesterday).
 * Does not execute dive gameplay or mutate streaks.
 */
import { useMemo, useState } from 'react';
import { dateStringFromDiveNumber } from '../domain/dailySchedule';
import type { DiveRunRecord } from '../domain/types';

interface ArchiveViewProps {
  todayDiveNumber: number;
  archiveCompleted: Record<number, DiveRunRecord>;
  dailyCompleted: Record<string, DiveRunRecord>;
  onPlayArchiveDive: (diveNumber: number) => void;
  onBack: () => void;
}

export function ArchiveView({
  todayDiveNumber,
  archiveCompleted,
  dailyCompleted,
  onPlayArchiveDive,
  onBack,
}: ArchiveViewProps) {
  const [query, setQuery] = useState('');

  const pastDives = useMemo(() => {
    const list: Array<{ diveNumber: number; dateEt: string; run?: DiveRunRecord }> = [];
    for (let d = todayDiveNumber - 1; d >= 1; d--) {
      const dateEt = dateStringFromDiveNumber(d);
      const run = archiveCompleted[d] ?? dailyCompleted[dateEt];
      list.push({ diveNumber: d, dateEt, run });
    }
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (item) =>
        String(item.diveNumber).includes(q) || item.dateEt.toLowerCase().includes(q)
    );
  }, [todayDiveNumber, archiveCompleted, dailyCompleted, query]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 24 }}>
      <div className="pixel-box" style={{ padding: 16 }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          FREE & UNLOCKED
        </div>
        <h2 className="krillion-title" style={{ fontSize: 24, marginTop: 4 }}>
          ARCHIVE ⟲
        </h2>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '8px 0 12px' }}>
          Replay any past Daily Dive (#1 through #{Math.max(1, todayDiveNumber - 1)}). Archive dives do not affect your daily streak.
        </p>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by dive # or YYYY-MM-DD..."
          style={{
            width: '100%',
            padding: '10px 12px',
            background: 'var(--surface-input)',
            border: '2px solid var(--border-bright)',
            color: '#ffffff',
            fontSize: 13,
          }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {pastDives.slice(0, 60).map((item) => (
          <div
            key={item.diveNumber}
            className="pixel-box"
            style={{
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
            }}
          >
            <div>
              <div className="pixel-label" style={{ fontSize: 13 }}>
                DIVE #{item.diveNumber}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                {item.dateEt}
                {item.run ? ` · Best: ${item.run.totalDepth.toLocaleString()}m (${item.run.totalScore} pts)` : ''}
              </div>
            </div>

            <button
              type="button"
              className={`btn-pixel ${item.run ? '' : 'btn-pink'}`}
              style={{ fontSize: 11, padding: '8px 12px' }}
              onClick={() => onPlayArchiveDive(item.diveNumber)}
            >
              {item.run ? 'REPLAY' : 'DIVE'}
            </button>
          </div>
        ))}
      </div>

      <button type="button" className="btn-pixel" onClick={onBack}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
