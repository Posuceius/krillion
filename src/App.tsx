/**
 * Owns hash routing, persistent user state, modal visibility, and dive session orchestration.
 * Does not implement answer matching, scoring formulas, or canvas rendering directly.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { OceanCanvas } from './art/OceanCanvas';
import { soundEngine } from './audio/soundEngine';
import { ArchiveView } from './components/ArchiveView';
import { DiveView } from './components/DiveView';
import { FaqView } from './components/FaqView';
import { LandingView } from './components/LandingView';
import { LogbookView } from './components/LogbookView';
import { type AppRoute, MenuModal } from './components/MenuModal';
import { PacksView } from './components/PacksView';
import { SettingsModal } from './components/SettingsModal';
import { TopBar } from './components/TopBar';
import { UnlimitedView } from './components/UnlimitedView';
import { WardrobeModal } from './components/WardrobeModal';
import {
  PROMPT_MANIFEST,
  TOTAL_ANSWER_COUNT,
  preloadPrompts,
} from './data';
import {
  dateStringFromDiveNumber,
  getDiveNumberForDate,
  getEasternDateString,
  getPromptsForDiveNumber,
  pickUnlimitedPrompts,
} from './domain/dailySchedule';
import { recordCompletedRun } from './domain/scoring';
import type {
  BuddyId,
  DiveMode,
  DiveRunRecord,
  PersistedAppState,
  Prompt,
  RoundResult,
  ThemedPack,
  UserSettings,
} from './domain/types';
import {
  loadPersistedState,
  resetPersistedState,
  savePersistedState,
} from './storage/persistence';

interface ActiveSession {
  key: string;
  mode: DiveMode;
  label: string;
  diveNumber?: number;
  dateEt?: string;
  packId?: string;
  chapterIndex?: number;
  prompts: Prompt[];
  initialRounds?: RoundResult[];
  initialIndex?: number;
  completedRun?: DiveRunRecord;
}

function parseHashRoute(): AppRoute {
  const hash = window.location.hash.replace(/^#\/?/, '').split('/')[0];
  switch (hash) {
    case 'archive':
      return 'archive';
    case 'packs':
      return 'packs';
    case 'unlimited':
      return 'unlimited';
    case 'account':
    case 'logbook':
      return 'logbook';
    case 'faq':
      return 'faq';
    default:
      return 'daily';
  }
}

function routeToHash(route: AppRoute): string {
  switch (route) {
    case 'daily':
      return '#/';
    case 'logbook':
      return '#/account';
    default:
      return `#/${route}`;
  }
}

export function App() {
  const [appState, setAppState] = useState<PersistedAppState>(() => loadPersistedState());
  const [route, setRoute] = useState<AppRoute>(() => parseHashRoute());
  const [activeSession, setActiveSession] = useState<ActiveSession | null>(null);
  const [loadingLabel, setLoadingLabel] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [canvasDepth, setCanvasDepth] = useState(0);
  const [recentUnlimitedPromptIds, setRecentUnlimitedPromptIds] = useState<string[]>([]);

  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [wardrobeOpen, setWardrobeOpen] = useState(false);

  const todayEt = getEasternDateString();
  const todayDiveNumber = getDiveNumberForDate(todayEt);
  const completedToday = appState.logbook.dailyCompleted[todayEt];

  const validInProgressDaily =
    appState.inProgressDaily && appState.inProgressDaily.dateEt === todayEt
      ? appState.inProgressDaily
      : null;

  useEffect(() => {
    savePersistedState(appState);
  }, [appState]);

  useEffect(() => {
    soundEngine.setEnabled(appState.settings.soundEnabled);
    document.body.classList.toggle('low-power', appState.settings.lowPowerMode);
    document.body.classList.toggle('colorblind', appState.settings.colorblindMode);
  }, [appState.settings]);

  useEffect(() => {
    const onHashChange = () => {
      setRoute(parseHashRoute());
      setActiveSession(null);
      setLoadingLabel(null);
      setLoadError(null);
      setCanvasDepth(0);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = useCallback((nextRoute: AppRoute) => {
    soundEngine.click();
    setActiveSession(null);
    setLoadingLabel(null);
    setLoadError(null);
    setCanvasDepth(0);
    setRoute(nextRoute);
    const nextHash = routeToHash(nextRoute);
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
    }
  }, []);

  const updateSetting = <K extends keyof UserSettings>(
    key: K,
    value: UserSettings[K]
  ) => {
    soundEngine.click();
    setAppState((prev) => ({
      ...prev,
      settings: {
        ...prev.settings,
        [key]: value,
      },
    }));
  };

  const todayPromptMeta = useMemo(
    () => getPromptsForDiveNumber(PROMPT_MANIFEST, todayDiveNumber),
    [todayDiveNumber]
  );

  const launchDiveSession = async (
    promptIds: string[],
    sessionBase: Omit<ActiveSession, 'prompts'>,
    targetDepth = 0
  ) => {
    setLoadError(null);
    setLoadingLabel(sessionBase.label);
    try {
      const prompts = await preloadPrompts(promptIds);
      setCanvasDepth(targetDepth);
      setActiveSession({
        ...sessionBase,
        prompts,
      });
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load prompt data');
    } finally {
      setLoadingLabel(null);
    }
  };

  const startDailyDive = () => {
    soundEngine.click();
    if (completedToday) {
      void launchDiveSession(
        completedToday.rounds.map((r) => r.promptId),
        {
          key: `daily-done-${todayDiveNumber}`,
          mode: 'daily',
          label: `DAILY DIVE #${todayDiveNumber}`,
          diveNumber: todayDiveNumber,
          dateEt: todayEt,
          completedRun: completedToday,
        },
        completedToday.totalDepth
      );
      return;
    }

    if (validInProgressDaily) {
      void launchDiveSession(validInProgressDaily.promptIds, {
        key: `daily-resume-${todayDiveNumber}`,
        mode: 'daily',
        label: `DAILY DIVE #${todayDiveNumber}`,
        diveNumber: todayDiveNumber,
        dateEt: todayEt,
        initialRounds: validInProgressDaily.rounds,
        initialIndex: validInProgressDaily.rounds.length,
      });
      return;
    }

    void launchDiveSession(
      todayPromptMeta.map((p) => p.id),
      {
        key: `daily-new-${todayDiveNumber}`,
        mode: 'daily',
        label: `DAILY DIVE #${todayDiveNumber}`,
        diveNumber: todayDiveNumber,
        dateEt: todayEt,
      }
    );
  };

  const startArchiveDive = (diveNumber: number) => {
    soundEngine.click();
    const promptMetas = getPromptsForDiveNumber(PROMPT_MANIFEST, diveNumber);
    const dateEt = dateStringFromDiveNumber(diveNumber);
    void launchDiveSession(
      promptMetas.map((p) => p.id),
      {
        key: `archive-${diveNumber}-${Date.now()}`,
        mode: 'archive',
        label: `ARCHIVE DIVE #${diveNumber}`,
        diveNumber,
        dateEt,
      }
    );
  };

  const startUnlimitedDive = () => {
    soundEngine.click();
    const promptMetas = pickUnlimitedPrompts(PROMPT_MANIFEST, recentUnlimitedPromptIds, 7);
    setRecentUnlimitedPromptIds((prev) =>
      [...promptMetas.map((p) => p.id), ...prev].slice(0, 28)
    );
    void launchDiveSession(
      promptMetas.map((p) => p.id),
      {
        key: `unlimited-${Date.now()}`,
        mode: 'unlimited',
        label: 'UNLIMITED DIVE',
      }
    );
  };

  const startPackChapter = (pack: ThemedPack, chapterIndex: number) => {
    soundEngine.click();
    const ch = pack.chapters[chapterIndex];
    void launchDiveSession(ch.promptIds, {
      key: `pack-${pack.id}-${chapterIndex}-${Date.now()}`,
      mode: 'pack',
      label: `${pack.title} · ${ch.title.toUpperCase()}`,
      packId: pack.id,
      chapterIndex,
    });
  };

  const handleDiveProgress = useCallback(
    (rounds: RoundResult[], currentIndex: number) => {
      if (!activeSession || activeSession.mode !== 'daily') return;
      setAppState((prev) => ({
        ...prev,
        inProgressDaily: {
          mode: 'daily',
          label: activeSession.label,
          diveNumber: activeSession.diveNumber,
          dateEt: activeSession.dateEt,
          promptIds: activeSession.prompts.map((p) => p.id),
          rounds,
          currentIndex,
        },
      }));
    },
    [activeSession]
  );

  const handleDiveComplete = useCallback((run: DiveRunRecord): BuddyId[] => {
    let unlocked: BuddyId[] = [];
    setAppState((prev) => {
      const { nextLogbook, newlyUnlockedBuddies } = recordCompletedRun(
        prev.logbook,
        run
      );
      unlocked = newlyUnlockedBuddies;
      return {
        ...prev,
        logbook: nextLogbook,
        inProgressDaily:
          run.mode === 'daily' ? null : prev.inProgressDaily,
      };
    });
    return unlocked;
  }, []);

  const showBuddyOnCanvas =
    Boolean(activeSession && !activeSession.completedRun) ||
    (!activeSession && !loadingLabel && route === 'daily');

  return (
    <div className="app-shell crt-scanlines">
      <OceanCanvas
        targetDepth={activeSession ? canvasDepth : route === 'daily' ? 0 : 320}
        buddyId={appState.equippedBuddy}
        showBuddy={showBuddyOnCanvas}
        isDiving={Boolean(activeSession || loadingLabel)}
        lowPower={appState.settings.lowPowerMode}
      />

      <div className="stage">
        <TopBar
          soundEnabled={appState.settings.soundEnabled}
          showExtraControls={!activeSession && !loadingLabel}
          onOpenMenu={() => {
            soundEngine.click();
            setMenuOpen(true);
          }}
          onToggleSound={() =>
            updateSetting('soundEnabled', !appState.settings.soundEnabled)
          }
          onOpenSettings={() => {
            soundEngine.click();
            setSettingsOpen(true);
          }}
          onOpenWardrobe={() => {
            soundEngine.click();
            setWardrobeOpen(true);
          }}
        />

        {loadError && (
          <div className="pixel-box" style={{ padding: 14, borderColor: 'var(--pink)', marginBottom: 12 }}>
            <div className="pixel-label" style={{ fontSize: 12, color: 'var(--pink)' }}>
              SONAR ERROR
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
              {loadError}
            </div>
          </div>
        )}

        {loadingLabel ? (
          <div className="pixel-box-cyan" style={{ padding: 24, marginTop: 48, textAlign: 'center' }}>
            <div className="pixel-label" style={{ fontSize: 12, color: 'var(--cyan)' }}>
              {loadingLabel}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 10 }}>
              SONAR LOCKING · LOADING PROMPTS...
            </div>
          </div>
        ) : activeSession ? (
          <DiveView
            key={activeSession.key}
            mode={activeSession.mode}
            label={activeSession.label}
            diveNumber={activeSession.diveNumber}
            dateEt={activeSession.dateEt}
            packId={activeSession.packId}
            chapterIndex={activeSession.chapterIndex}
            prompts={activeSession.prompts}
            initialRounds={activeSession.initialRounds}
            initialIndex={activeSession.initialIndex}
            completedRun={activeSession.completedRun}
            settings={appState.settings}
            onProgress={handleDiveProgress}
            onComplete={handleDiveComplete}
            onDepthChange={setCanvasDepth}
            onPlayAgain={
              activeSession.mode === 'unlimited'
                ? startUnlimitedDive
                : activeSession.mode === 'archive' && activeSession.diveNumber
                  ? () => startArchiveDive(activeSession.diveNumber!)
                  : undefined
            }
            playAgainLabel={
              activeSession.mode === 'unlimited' ? 'NEXT DIVE ∞' : 'REPLAY ⟲'
            }
            onGoHome={() => {
              setActiveSession(null);
              setCanvasDepth(0);
              navigate('daily');
            }}
            onOpenWardrobe={() => setWardrobeOpen(true)}
          />
        ) : route === 'archive' ? (
          <ArchiveView
            todayDiveNumber={todayDiveNumber}
            archiveCompleted={appState.logbook.archiveCompleted}
            dailyCompleted={appState.logbook.dailyCompleted}
            onPlayArchiveDive={startArchiveDive}
            onBack={() => navigate('daily')}
          />
        ) : route === 'unlimited' ? (
          <UnlimitedView
            promptCount={PROMPT_MANIFEST.length}
            totalAnswers={TOTAL_ANSWER_COUNT}
            runs={appState.logbook.unlimitedRuns}
            onStartUnlimited={startUnlimitedDive}
            onBack={() => navigate('daily')}
          />
        ) : route === 'packs' ? (
          <PacksView
            packCompleted={appState.logbook.packCompleted}
            onStartPackChapter={startPackChapter}
            onBack={() => navigate('daily')}
          />
        ) : route === 'logbook' ? (
          <LogbookView
            logbook={appState.logbook}
            settings={appState.settings}
            onResetAll={() => {
              soundEngine.click();
              setAppState(resetPersistedState());
            }}
            onOpenWardrobe={() => setWardrobeOpen(true)}
            onBack={() => navigate('daily')}
          />
        ) : route === 'faq' ? (
          <FaqView
            promptCount={PROMPT_MANIFEST.length}
            totalAnswers={TOTAL_ANSWER_COUNT}
            onBack={() => navigate('daily')}
          />
        ) : (
          <LandingView
            diveNumber={todayDiveNumber}
            promptCount={PROMPT_MANIFEST.length}
            totalAnswers={TOTAL_ANSWER_COUNT}
            completedToday={completedToday}
            inProgressDaily={validInProgressDaily}
            currentStreak={appState.logbook.currentStreak}
            onStartDaily={startDailyDive}
            onOpenArchive={() => navigate('archive')}
            onOpenPacks={() => navigate('packs')}
            onOpenUnlimited={() => navigate('unlimited')}
          />
        )}
      </div>

      {menuOpen && (
        <MenuModal
          currentRoute={route}
          onNavigate={navigate}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenWardrobe={() => setWardrobeOpen(true)}
          onClose={() => setMenuOpen(false)}
        />
      )}

      {settingsOpen && (
        <SettingsModal
          settings={appState.settings}
          onChangeSetting={updateSetting}
          onOpenLogbook={() => navigate('logbook')}
          onOpenFaq={() => navigate('faq')}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {wardrobeOpen && (
        <WardrobeModal
          bestStreak={appState.logbook.bestStreak}
          equippedBuddy={appState.equippedBuddy}
          onEquip={(buddy) => {
            soundEngine.click();
            setAppState((prev) => ({ ...prev, equippedBuddy: buddy }));
          }}
          onClose={() => setWardrobeOpen(false)}
        />
      )}
    </div>
  );
}
