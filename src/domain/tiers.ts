/**
 * Owns static definitions for the 6 rarity tiers, ocean zones, depth milestones, and 9 Dive Buddies.
 * Does not mutate player state or calculate streaks.
 */
import type {
  BuddyDefinition,
  BuddyId,
  DepthMilestone,
  OceanZone,
  TierDefinition,
  TierId,
} from './types';

export const TIER_ORDER: TierId[] = [
  'miss',
  'plankton',
  'tooclever',
  'schooler',
  'rare',
  'deepcut',
  'krillion',
];

export const ACCEPTED_TIER_ORDER: Exclude<TierId, 'miss'>[] = [
  'plankton',
  'tooclever',
  'schooler',
  'rare',
  'deepcut',
  'krillion',
];

export const TIERS: Record<TierId, TierDefinition> = {
  miss: {
    id: 'miss',
    label: 'NO ECHO',
    shortLabel: 'MISS',
    points: 0,
    depthMeters: 0,
    emoji: '💨',
    flavor: 'No echo - drifted on the surface.',
    color: '#64748b',
    colorblindColor: '#94a3b8',
  },
  plankton: {
    id: 'plankton',
    label: 'PLANKTON',
    shortLabel: 'PLANKTON',
    points: 5,
    depthMeters: 50,
    emoji: '🫧',
    flavor: 'Surface level - everyone knows this one.',
    color: '#93c5fd',
    colorblindColor: '#56b4e9',
  },
  tooclever: {
    id: 'tooclever',
    label: 'TOO CLEVER',
    shortLabel: 'CLEVER',
    points: 15,
    depthMeters: 150,
    emoji: '🪝',
    flavor: 'Took the bait - feels niche, widely picked.',
    color: '#f59e0b',
    colorblindColor: '#e69f00',
  },
  schooler: {
    id: 'schooler',
    label: 'SCHOOLER',
    shortLabel: 'SCHOOLER',
    points: 30,
    depthMeters: 300,
    emoji: '🐟',
    flavor: 'Solid - swims with the school.',
    color: '#38bdf8',
    colorblindColor: '#0072b2',
  },
  rare: {
    id: 'rare',
    label: 'RARE',
    shortLabel: 'RARE',
    points: 60,
    depthMeters: 600,
    emoji: '🦑',
    flavor: 'Deep swimmer - well off the beaten path.',
    color: '#a855f7',
    colorblindColor: '#cc79a7',
  },
  deepcut: {
    id: 'deepcut',
    label: 'DEEP CUT',
    shortLabel: 'DEEP CUT',
    points: 85,
    depthMeters: 850,
    emoji: '🐡',
    flavor: 'Abyssal find - specialist knowledge.',
    color: '#ec4899',
    colorblindColor: '#d55e00',
  },
  krillion: {
    id: 'krillion',
    label: 'ONE IN A KRILLION',
    shortLabel: 'KRILLION',
    points: 100,
    depthMeters: 1000,
    emoji: '🦐',
    flavor: 'One in a Krillion! Trench-floor gem.',
    color: '#fde047',
    colorblindColor: '#f0e442',
  },
};

export const OCEAN_ZONES: OceanZone[] = [
  {
    id: 'sunlight',
    name: 'SUNLIGHT ZONE',
    subtitle: 'Epipelagic (0 - 200m)',
    minDepth: 0,
    maxDepth: 200,
    badgeColor: '#38bdf8',
  },
  {
    id: 'twilight',
    name: 'TWILIGHT ZONE',
    subtitle: 'Mesopelagic (200 - 1,000m)',
    minDepth: 200,
    maxDepth: 1000,
    badgeColor: '#60a5fa',
  },
  {
    id: 'midnight',
    name: 'MIDNIGHT ZONE',
    subtitle: 'Bathypelagic (1,000 - 4,000m)',
    minDepth: 1000,
    maxDepth: 4000,
    badgeColor: '#a855f7',
  },
  {
    id: 'abyssal',
    name: 'ABYSSAL ZONE',
    subtitle: 'Abyssopelagic (4,000 - 6,000m)',
    minDepth: 4000,
    maxDepth: 6000,
    badgeColor: '#ec4899',
  },
  {
    id: 'hadal',
    name: 'HADAL ZONE',
    subtitle: 'Hadopelagic Trench (6,000 - 7,000m)',
    minDepth: 6000,
    maxDepth: 7000,
    badgeColor: '#fde047',
  },
];

export const DEPTH_MILESTONES: DepthMilestone[] = [
  { depth: 200, label: 'most sunlight stops here' },
  { depth: 332, label: 'deepest scuba dive ever - 332m' },
  { depth: 400, label: 'sperm whales hunt below here' },
  { depth: 535, label: 'emperor penguins dive this deep' },
  { depth: 670, label: 'pressure: 67x the surface' },
  { depth: 850, label: 'siphonophore drift zone' },
  { depth: 1000, label: 'THE MIDNIGHT ZONE', isZoneHeader: true },
  { depth: 1800, label: 'giant squid hunting ground' },
  { depth: 2400, label: 'hydrothermal vent plumes' },
  { depth: 3800, label: 'Titanic wreck - 3,800m' },
  { depth: 4000, label: 'THE ABYSSAL ZONE', isZoneHeader: true },
  { depth: 5200, label: 'abyssal plains - total dark' },
  { depth: 6000, label: 'THE HADAL ZONE', isZoneHeader: true },
  { depth: 7000, label: 'trench floor - 7,000m max' },
];

export const BUDDIES: Record<BuddyId, BuddyDefinition> = {
  krill: {
    id: 'krill',
    name: 'THE KRILL',
    requiredStreak: 0,
    description: 'Small, brave, and bioluminescent.',
  },
  schooler: {
    id: 'schooler',
    name: 'SCHOOLER',
    requiredStreak: 5,
    description: '5-day streak silver reef runner.',
  },
  squid: {
    id: 'squid',
    name: 'RARE SQUID',
    requiredStreak: 14,
    description: '14-day streak twilight jetter.',
  },
  angler: {
    id: 'angler',
    name: 'DEEP CUT ANGLER',
    requiredStreak: 30,
    description: '30-day streak lantern stalker.',
  },
  evil_krill: {
    id: 'evil_krill',
    name: 'EVIL KRILL',
    requiredStreak: 45,
    description: '45-day streak crimson rebel.',
  },
  hackmanite: {
    id: 'hackmanite',
    name: 'HACKMANITE',
    requiredStreak: 60,
    description: '60-day streak mineral shifter.',
  },
  fossil_krill: {
    id: 'fossil_krill',
    name: 'FOSSIL KRILL',
    requiredStreak: 75,
    description: '75-day streak ancient relic.',
  },
  mantis_shrimp: {
    id: 'mantis_shrimp',
    name: 'MANTIS SHRIMP',
    requiredStreak: 100,
    description: '100-day streak prismatic puncher.',
  },
  leviathan: {
    id: 'leviathan',
    name: 'LEVIATHAN',
    requiredStreak: 150,
    description: '150-day streak trench sovereign.',
  },
};

export const BUDDY_ORDER: BuddyId[] = [
  'krill',
  'schooler',
  'squid',
  'angler',
  'evil_krill',
  'hackmanite',
  'fossil_krill',
  'mantis_shrimp',
  'leviathan',
];

export function getOceanZone(depthMeters: number): OceanZone {
  for (let i = OCEAN_ZONES.length - 1; i >= 0; i--) {
    if (depthMeters >= OCEAN_ZONES[i].minDepth) {
      return OCEAN_ZONES[i];
    }
  }
  return OCEAN_ZONES[0];
}
