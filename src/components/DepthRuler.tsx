/**
 * Owns the scrolling right-hand ocean depth ruler, milestone labels, and YOU indicator during dives.
 * Does not render the background canvas or calculate scores.
 */
import { DEPTH_MILESTONES } from '../domain/tiers';

interface DepthRulerProps {
  currentDepth: number;
}

const WINDOW_SPAN = 420;

export function DepthRuler({ currentDepth }: DepthRulerProps) {
  const minD = Math.max(0, currentDepth - 180);
  const maxD = minD + WINDOW_SPAN;

  const tickStep = 50;
  const firstTick = Math.ceil(minD / tickStep) * tickStep;
  const ticks: number[] = [];
  for (let d = firstTick; d <= maxD; d += tickStep) {
    ticks.push(d);
  }

  const visibleMilestones = DEPTH_MILESTONES.filter(
    (m) => m.depth >= minD && m.depth <= maxD
  );

  const toPercent = (d: number) => ((d - minD) / WINDOW_SPAN) * 100;
  const youPct = Math.max(4, Math.min(96, toPercent(currentDepth)));

  return (
    <div className="depth-ruler" aria-hidden="true">
      {ticks.map((d) => {
        const pct = toPercent(d);
        const isMajor = d % 100 === 0;
        return (
          <div
            key={d}
            style={{
              position: 'absolute',
              right: 0,
              top: `${pct}%`,
              width: isMajor ? 10 : 5,
              borderTop: `1px solid ${isMajor ? 'rgba(155,180,212,0.5)' : 'rgba(155,180,212,0.25)'}`,
            }}
          >
            {isMajor && <span className="ruler-tick-label">-{d}m</span>}
          </div>
        );
      })}

      {visibleMilestones.map((m) => (
        <div
          key={m.depth}
          className={`ruler-milestone ${m.isZoneHeader ? 'zone' : ''}`}
          style={{ top: `${toPercent(m.depth)}%` }}
        >
          {m.label}
        </div>
      ))}

      <div className="ruler-you" style={{ top: `${youPct}%` }}>
        <span>YOU</span>
        <span>◄</span>
      </div>
    </div>
  );
}
