/**
 * Owns the top navigation bar with Menu, Sound mute, Settings, and Wardrobe icon buttons.
 * Does not render modal dialogs or track audio state internally.
 */
interface TopBarProps {
  soundEnabled: boolean;
  showExtraControls?: boolean;
  onOpenMenu: () => void;
  onToggleSound: () => void;
  onOpenSettings: () => void;
  onOpenWardrobe: () => void;
}

export function TopBar({
  soundEnabled,
  showExtraControls = true,
  onOpenMenu,
  onToggleSound,
  onOpenSettings,
  onOpenWardrobe,
}: TopBarProps) {
  return (
    <header className="top-bar">
      <button
        type="button"
        className="icon-btn"
        aria-label="Open menu"
        title="Open menu"
        onClick={onOpenMenu}
      >
        <svg width="18" height="14" viewBox="0 0 18 14" fill="currentColor" aria-hidden="true">
          <rect x="1" y="1" width="16" height="2" />
          <rect x="1" y="6" width="16" height="2" />
          <rect x="1" y="11" width="16" height="2" />
        </svg>
      </button>

      <div className="top-bar-right">
        <button
          type="button"
          className="icon-btn"
          aria-label={soundEnabled ? 'Turn sound off' : 'Turn sound on'}
          title={soundEnabled ? 'Turn sound off' : 'Turn sound on'}
          onClick={onToggleSound}
        >
          {soundEnabled ? (
            <svg width="18" height="16" viewBox="0 0 18 16" fill="currentColor" aria-hidden="true">
              <path d="M2 5h3l4-4v14l-4-4H2V5zm10.5 3c0-1.6-.9-3-2.2-3.7v7.4c1.3-.7 2.2-2.1 2.2-3.7zm2.5 0c0-2.9-1.6-5.4-4-6.7v1.8c1.5 1 2.5 2.8 2.5 4.9s-1 3.9-2.5 4.9v1.8c2.4-1.3 4-3.8 4-6.7z" />
            </svg>
          ) : (
            <svg width="18" height="16" viewBox="0 0 18 16" fill="currentColor" aria-hidden="true">
              <path d="M2 5h3l4-4v14l-4-4H2V5zm10 1l4 4m0-4l-4 4" stroke="currentColor" strokeWidth="2" />
            </svg>
          )}
        </button>

        {showExtraControls && (
          <>
            <button
              type="button"
              className="icon-btn"
              aria-label="Open settings"
              title="Open settings"
              onClick={onOpenSettings}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M19.4 13a7.9 7.9 0 0 0 .1-1 7.9 7.9 0 0 0-.1-1l2.1-1.6-2-3.5-2.5 1a7.4 7.4 0 0 0-1.7-1l-.4-2.7h-4l-.4 2.7a7.4 7.4 0 0 0-1.7 1l-2.5-1-2 3.5L5.4 11a7.9 7.9 0 0 0-.1 1 7.9 7.9 0 0 0 .1 1l-2.1 1.6 2 3.5 2.5-1a7.4 7.4 0 0 0 1.7 1l.4 2.7h4l.4-2.7a7.4 7.4 0 0 0 1.7-1l2.5 1 2-3.5-2.1-1.6zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z" />
              </svg>
            </button>

            <button
              type="button"
              className="icon-btn"
              aria-label="Open wardrobe"
              title="Open wardrobe"
              onClick={onOpenWardrobe}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M16 4l4 3-2 4-2-1v10H8V10l-2 1-2-4 4-3h2a2 2 0 0 0 4 0h2z" />
              </svg>
            </button>
          </>
        )}
      </div>
    </header>
  );
}
