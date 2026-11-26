/**
 * Owns the retro hamburger navigation modal linking to all single-player modes, wardrobe, and settings.
 * Does not own route state or modal open flags.
 */
import { useEffect } from 'react';

export type AppRoute =
  | 'daily'
  | 'unlimited'
  | 'archive'
  | 'packs'
  | 'logbook'
  | 'faq';

interface MenuModalProps {
  currentRoute: AppRoute;
  onNavigate: (route: AppRoute) => void;
  onOpenSettings: () => void;
  onOpenWardrobe: () => void;
  onClose: () => void;
}

export function MenuModal({
  currentRoute,
  onNavigate,
  onOpenSettings,
  onOpenWardrobe,
  onClose,
}: MenuModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const items: Array<{ id: AppRoute; label: string; icon: string }> = [
    { id: 'daily', label: 'DAILY DIVE', icon: '↓' },
    { id: 'unlimited', label: 'UNLIMITED', icon: '∞' },
    { id: 'archive', label: 'ARCHIVE', icon: '⟲' },
    { id: 'packs', label: 'THEMED PACKS', icon: '⊞' },
    { id: 'logbook', label: 'MY KRILLION', icon: '♟' },
    { id: 'faq', label: 'FAQ', icon: '?' },
  ];

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Menu" onClick={onClose}>
      <div className="modal-panel scroll-thin" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
              KRILLION
            </div>
            <h2 className="krillion-title" style={{ fontSize: 28, marginTop: 2 }}>
              MENU
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close menu">
            X
          </button>
        </div>

        <div className="divider-line">DIVE IN</div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 10,
          }}
        >
          {items.map((item) => {
            const active = currentRoute === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className="btn-pixel"
                style={{
                  flexDirection: 'column',
                  padding: '16px 10px',
                  borderColor: active ? 'var(--pink)' : 'var(--border-dim)',
                  color: active ? '#ff8fb1' : 'var(--text-primary)',
                }}
                onClick={() => {
                  onNavigate(item.id);
                  onClose();
                }}
              >
                <span style={{ fontSize: 20 }}>{item.icon}</span>
                <span style={{ fontSize: 11 }}>{item.label}</span>
              </button>
            );
          })}

          <button
            type="button"
            className="btn-pixel"
            style={{ flexDirection: 'column', padding: '16px 10px' }}
            onClick={() => {
              onClose();
              onOpenWardrobe();
            }}
          >
            <span style={{ fontSize: 20 }}>🦐</span>
            <span style={{ fontSize: 11 }}>WARDROBE</span>
          </button>

          <button
            type="button"
            className="btn-pixel"
            style={{ flexDirection: 'column', padding: '16px 10px' }}
            onClick={() => {
              onClose();
              onOpenSettings();
            }}
          >
            <span style={{ fontSize: 20 }}>⚙</span>
            <span style={{ fontSize: 11 }}>SETTINGS</span>
          </button>
        </div>

        <p
          style={{
            marginTop: 20,
            marginBottom: 0,
            fontSize: 11,
            color: 'var(--text-muted)',
            textAlign: 'center',
          }}
        >
          one in a krillion · static single-player edition
        </p>
      </div>
    </div>
  );
}
