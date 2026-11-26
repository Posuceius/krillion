/**
 * Owns the static FAQ screen documenting Krillion rules, rarity tiers, answer sources, and local storage.
 * Does not manage navigation state beyond invoking its onBack callback.
 */
interface FaqViewProps {
  promptCount: number;
  totalAnswers: number;
  onBack: () => void;
}

export function FaqView({ promptCount, totalAnswers, onBack }: FaqViewProps) {
  const nonRepeatDays = Math.floor(promptCount / 7);
  const faqItems = [
    {
      q: 'How does Krillion work?',
      a: 'Each Daily Dive gives you 7 prompts and 25 seconds per prompt. Every valid answer scores points based on how rare it is. Every point sinks you 10 meters deeper into the ocean - up to 7,000 meters total.',
    },
    {
      q: 'Where do all the answers and rarity scores come from?',
      a: `This static edition packs ${totalAnswers.toLocaleString()} answers across ${promptCount.toLocaleString()} distinct prompts (${nonRepeatDays}+ consecutive days with zero repeated prompts), built from curated seed lists, Wikidata encyclopedic records (ranked by Wikipedia sitelinks), and English dictionary + word-frequency datasets.`,
    },
    {
      q: 'What are the 6 rarity tiers?',
      a: 'Plankton (5 pts / 50m), Too Clever (15 pts / 150m), Schooler (30 pts / 300m), Rare (60 pts / 600m), Deep Cut (85 pts / 850m), and One in a Krillion (100 pts / 1,000m).',
    },
    {
      q: 'Why does "Too Clever" score less than "Schooler"?',
      a: 'Too Clever catches answers that feel clever to think of on the spot, which means thousands of players converge on the exact same choice. True Schooler and Rare answers stay genuinely off the beaten path.',
    },
    {
      q: 'How do answer corrections and aliases work?',
      a: 'Accents, punctuation, leading articles ("the", "a"), common plurals, and alternate spellings are matched automatically. Small typos are caught using edit-distance matching and previewed when Answer Corrections is ON.',
    },
    {
      q: 'How are Daily Dives and streaks tracked?',
      a: 'Daily Dives reset at midnight Eastern Time (ET) using a deterministic daily schedule, so everyone gets the same 7 prompts for that dive number. Your streaks, scores, and unlocked Dive Buddies are stored locally in your browser.',
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 24 }}>
      <div className="pixel-box" style={{ padding: 16 }}>
        <div className="pixel-label" style={{ fontSize: 11, color: 'var(--cyan)' }}>
          HOW IT WORKS
        </div>
        <h2 className="krillion-title" style={{ fontSize: 24, marginTop: 4 }}>
          FAQ
        </h2>
      </div>

      {faqItems.map((item) => (
        <div key={item.q} className="pixel-box" style={{ padding: 14 }}>
          <div className="pixel-label" style={{ fontSize: 12, color: 'var(--cyan)' }}>
            {item.q}
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '8px 0 0', lineHeight: 1.6 }}>
            {item.a}
          </p>
        </div>
      ))}

      <button type="button" className="btn-pixel" onClick={onBack}>
        ← BACK TO SURFACE
      </button>
    </div>
  );
}
