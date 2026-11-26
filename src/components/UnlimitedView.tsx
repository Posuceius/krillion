/**
 * Owns the Unlimited mode landing card, personal best summary, and recent unlimited dive history.
 * Does not select prompts or execute gameplay rounds.
 */
import { getOceanZone } from '../domain/tiers';
import type { DiveRunRecord } from '../domain/types';

interface UnlimitedViewProps {
  promptCount: number;
  totalAnswers: number;
  runs: DiveRunRecord[];
  onStartUnlimited: () => void;
  onBack: () => void;
}

export function UnlimitedView({
  promptCount,
  totalAnswers,
  runs,
  onStartUnlimited,
  onBack,
}: UnlimitedViewProps) {
  const bestRun = runs.reduce<DiveRunRecord | null>(
    (best, curr) => (!best || curr.totalScore > best.totalScore ? curr : best),
    null
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 24 }}>
      <div className="pixel-box-cyan" style={{ padding: 18, textAlign: 'center' }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          THE ENDLESS DIVE
        </div>
        <h2 className="krillion-title" style={{ fontSize: 26, marginTop: 4 }}>
          UNLIMITED ∞
        </h2>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '10px 0 16px', lineHeight: 1.5 }}>
          Fresh 7-prompt rounds drawn across {promptCount} prompts and {totalAnswers.toLocaleString()} curated & encyclopedic answers. Dive as deep and as often as you want.
        </p>

        <button
          type="button"
          className="btn-pixel btn-primary-cyan"
          style={{ width: '100%' }}
          onClick={onStartUnlimited}
        >
          ▼ START UNLIMITED DIVE ▼
        </button>

        {bestRun && (
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
            Personal Best: {bestRun.totalDepth.toLocaleString()}m ({bestRun.totalScore}/700 pts)
          </div>
        )}
      </div>

      {runs.length > 0 && (
        <>
          <div className="divider-line">RECENT UNLIMITED DIVES</div>
          {runs.slice(0, 10).map((run) => {
            const zone = getOceanZone(run.totalDepth);
            return (
              <div
                key={run.id}
                className="pixel-box"
                style={{
                  padding: '10px 14px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div className="pixel-label" style={{ fontSize: 12 }}>
                    {run.totalDepth.toLocaleString()}m · {zone.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {new Date(run.completedAt).toLocaleDateString()}
                  </div>
                </div>
                <div className="pixel-label" style={{ fontSize: 12, color: 'var(--cyan)' }}>
                  {run.totalScore}/700
                </div>
              </div>
            );
          })}
        </>
      )}

      <button type="button" className="btn-pixel" onClick={onBack}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
