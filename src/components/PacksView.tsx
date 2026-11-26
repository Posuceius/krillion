/**
 * Owns the Themed Packs selector and chapter list for Words, Movies, Sports, and Geography packs.
 * Does not load prompt chunks or run gameplay rounds.
 */
import { useState } from 'react';
import { THEMED_PACKS } from '../data';
import type { DiveRunRecord, ThemedPack } from '../domain/types';

interface PacksViewProps {
  packCompleted: Record<string, DiveRunRecord>;
  onStartPackChapter: (pack: ThemedPack, chapterIndex: number) => void;
  onBack: () => void;
}

export function PacksView({
  packCompleted,
  onStartPackChapter,
  onBack,
}: PacksViewProps) {
  const [selectedPackId, setSelectedPackId] = useState<ThemedPack['id'] | null>(null);
  const selectedPack = THEMED_PACKS.find((p) => p.id === selectedPackId) ?? null;

  if (selectedPack) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 24 }}>
        <div className="pixel-box" style={{ padding: 16 }}>
          <div className="pixel-label" style={{ fontSize: 11, color: selectedPack.accentColor }}>
            THEMED PACK · 5 PROMPTS PER STAGE
          </div>
          <h2 className="krillion-title" style={{ fontSize: 22, marginTop: 4 }}>
            {selectedPack.title}
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '6px 0 0' }}>
            {selectedPack.subtitle}
          </p>
        </div>

        {selectedPack.chapters.map((ch, idx) => {
          const rec = packCompleted[`${selectedPack.id}:${idx}`];
          return (
            <div
              key={ch.id}
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
                <div className="pixel-label" style={{ fontSize: 12 }}>
                  {ch.title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 3 }}>
                  {ch.subtitle}
                </div>
                {rec && (
                  <div style={{ fontSize: 11, color: 'var(--cyan)', marginTop: 4 }}>
                    Best: {rec.totalDepth.toLocaleString()}m ({rec.totalScore}/{rec.maxScore} pts)
                  </div>
                )}
              </div>

              <button
                type="button"
                className={`btn-pixel ${rec ? '' : 'btn-pink'}`}
                style={{ fontSize: 11, padding: '8px 12px', flexShrink: 0 }}
                onClick={() => onStartPackChapter(selectedPack, idx)}
              >
                {rec ? 'REPLAY' : 'PLAY'}
              </button>
            </div>
          );
        })}

        <button
          type="button"
          className="btn-pixel"
          onClick={() => setSelectedPackId(null)}
        >
          ← ALL THEMED PACKS
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 24 }}>
      <div className="pixel-box" style={{ padding: 16 }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          100 SPECIALIZED PROMPTS · FREE & UNLOCKED
        </div>
        <h2 className="krillion-title" style={{ fontSize: 24, marginTop: 4 }}>
          THEMED PACKS
        </h2>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '8px 0 0' }}>
          Dive into topic-focused 5-prompt stages across 4 themed collections.
        </p>
      </div>

      {THEMED_PACKS.map((pack) => {
        const doneCount = pack.chapters.filter(
          (_, idx) => Boolean(packCompleted[`${pack.id}:${idx}`])
        ).length;
        return (
          <button
            key={pack.id}
            type="button"
            className="pixel-box"
            style={{
              padding: 16,
              textAlign: 'left',
              cursor: 'pointer',
              borderColor: pack.accentColor,
              color: 'inherit',
            }}
            onClick={() => setSelectedPackId(pack.id)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="pixel-label" style={{ fontSize: 15, color: pack.accentColor }}>
                {pack.title}
              </div>
              <div className="pixel-label" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                {doneCount} / {pack.chapters.length} {pack.unitLabel}
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              {pack.subtitle}
            </div>
          </button>
        );
      })}

      <button type="button" className="btn-pixel" onClick={onBack}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
