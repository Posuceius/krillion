/**
 * Owns the Wardrobe modal grid displaying all 9 Dive Buddies, streak locks, and equip controls.
 * Does not track streaks or persist the equipped buddy directly.
 */
import { useEffect } from 'react';
import { BUDDY_SPRITES } from '../art/pixelSprites';
import { PixelSpriteSvg } from '../art/PixelSpriteSvg';
import { BUDDIES, BUDDY_ORDER } from '../domain/tiers';
import type { BuddyId } from '../domain/types';

interface WardrobeModalProps {
  bestStreak: number;
  equippedBuddy: BuddyId;
  onEquip: (buddy: BuddyId) => void;
  onClose: () => void;
}

export function WardrobeModal({
  bestStreak,
  equippedBuddy,
  onEquip,
  onClose,
}: WardrobeModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Wardrobe" onClick={onClose}>
      <div className="modal-panel scroll-thin" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
              DIVE BUDDIES
            </div>
            <h2 className="krillion-title" style={{ fontSize: 24, marginTop: 2 }}>
              WARDROBE
            </h2>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
              Best daily streak: {bestStreak} {bestStreak === 1 ? 'day' : 'days'}
            </div>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close wardrobe">
            X
          </button>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 10,
          }}
        >
          {BUDDY_ORDER.map((id) => {
            const buddy = BUDDIES[id];
            const unlocked = bestStreak >= buddy.requiredStreak;
            const equipped = equippedBuddy === id;
            return (
              <button
                key={id}
                type="button"
                disabled={!unlocked}
                onClick={() => onEquip(id)}
                className="btn-pixel"
                style={{
                  flexDirection: 'column',
                  padding: '14px 10px',
                  borderColor: equipped
                    ? 'var(--cyan)'
                    : unlocked
                      ? 'var(--border-bright)'
                      : 'var(--border-dim)',
                  boxShadow: equipped ? '0 0 14px var(--cyan-glow)' : 'none',
                  opacity: unlocked ? 1 : 0.65,
                }}
              >
                <PixelSpriteSvg sprite={BUDDY_SPRITES[id]} size={48} silhouette={!unlocked} />
                <span
                  className="pixel-label"
                  style={{
                    fontSize: 11,
                    color: equipped ? 'var(--cyan)' : 'var(--text-primary)',
                    marginTop: 4,
                  }}
                >
                  {buddy.name}
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {buddy.requiredStreak === 0
                    ? 'DEFAULT'
                    : unlocked
                      ? equipped
                        ? 'EQUIPPED'
                        : `${buddy.requiredStreak}-DAY UNLOCKED`
                      : `${buddy.requiredStreak}-DAY STREAK`}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
