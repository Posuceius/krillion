/**
 * Owns the Settings modal switches (low-power, colorblind, corrections, clear rejected, share link).
 * Does not persist settings directly (delegates via onChangeSetting).
 */
import { useEffect } from 'react';
import type { UserSettings } from '../domain/types';

interface SettingsModalProps {
  settings: UserSettings;
  onChangeSetting: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void;
  onOpenLogbook: () => void;
  onOpenFaq: () => void;
  onClose: () => void;
}

interface ToggleRowProps {
  title: string;
  description: string;
  value: boolean;
  onToggle: () => void;
}

function ToggleRow({ title, description, value, onToggle }: ToggleRowProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 14,
        padding: '12px 0',
        borderBottom: '1px solid rgba(30, 53, 86, 0.55)',
      }}
    >
      <div>
        <div className="pixel-label" style={{ fontSize: 13, color: 'var(--text-primary)' }}>
          {title}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.4 }}>
          {description}
        </div>
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={value}
        aria-label={title}
        className={`toggle-switch ${value ? 'on' : 'off'}`}
        onClick={onToggle}
      >
        <span className="toggle-knob">{value ? 'ON' : 'OFF'}</span>
      </button>
    </div>
  );
}

export function SettingsModal({
  settings,
  onChangeSetting,
  onOpenLogbook,
  onOpenFaq,
  onClose,
}: SettingsModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Settings" onClick={onClose}>
      <div className="modal-panel scroll-thin" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
              KRILLION
            </div>
            <h2 className="krillion-title" style={{ fontSize: 26, marginTop: 2 }}>
              SETTINGS
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close settings">
            X
          </button>
        </div>

        <ToggleRow
          title="LOW-POWER MODE"
          description="Lighter graphics and fewer background animations."
          value={settings.lowPowerMode}
          onToggle={() => onChangeSetting('lowPowerMode', !settings.lowPowerMode)}
        />

        <ToggleRow
          title="COLORBLIND MODE"
          description="Brighter text and more separated tier colors."
          value={settings.colorblindMode}
          onToggle={() => onChangeSetting('colorblindMode', !settings.colorblindMode)}
        />

        <ToggleRow
          title="ANSWER CORRECTIONS"
          description="Preview corrected answers before scoring. Off accepts them immediately."
          value={settings.answerCorrections}
          onToggle={() => onChangeSetting('answerCorrections', !settings.answerCorrections)}
        />

        <ToggleRow
          title="CLEAR REJECTED ENTRIES"
          description="Empty the answer box after a failed attempt."
          value={settings.clearRejectedEntries}
          onToggle={() => onChangeSetting('clearRejectedEntries', !settings.clearRejectedEntries)}
        />

        <ToggleRow
          title="SHARE LINK"
          description="Add the game URL under shared results."
          value={settings.shareLink}
          onToggle={() => onChangeSetting('shareLink', !settings.shareLink)}
        />

        <div className="divider-line">LOGBOOK & INFO</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button
            type="button"
            className="btn-pixel"
            style={{ width: '100%' }}
            onClick={() => {
              onClose();
              onOpenLogbook();
            }}
          >
            MY KRILLION LOGBOOK →
          </button>

          <button
            type="button"
            className="btn-pixel"
            style={{ width: '100%' }}
            onClick={() => {
              onClose();
              onOpenFaq();
            }}
          >
            READ FAQ ?
          </button>
        </div>
      </div>
    </div>
  );
}
