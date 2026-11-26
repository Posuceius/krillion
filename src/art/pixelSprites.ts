/**
 * Owns pixel-art sprite matrices and color palettes for Dive Buddies, rarity tiers, and ambient fish.
 * Does not perform canvas or DOM rendering.
 */
import type { BuddyId, TierId } from '../domain/types';

export interface PixelSpriteData {
  width: number;
  height: number;
  rows: string[];
  palette: Record<string, string>;
}

const KRILL_ROWS = [
  '....PP..PP......',
  '...P......P.....',
  '.....RRRR.......',
  '....RRRRWRR.....',
  '...RRRRRRRR.....',
  '...RRRRRR.......',
  '....RRRRR.......',
  '...LLRRRLL......',
  '....RRRRR.......',
  '...LLRRRR.......',
  '.....RRRRR......',
  '......RRRRR.....',
  '.....LL.TTTT....',
  '........TTTTT...',
  '.........TT.....',
  '................',
];

const FISH_ROWS = [
  '................',
  '................',
  '.....BBBBBB.....',
  '...BBBBBBBBBB...',
  '..BBBBBBWBBBBB..',
  '.BBBBBBBBBBBBBB.',
  '.BBBBBBBBBBBBBB.',
  '..BBBBBBBBBBBBB.',
  '...BBBBBBBBBBB..',
  '.....BBBBBBB....',
  '.......BB.......',
  '................',
  '................',
  '................',
  '................',
  '................',
];

const SCHOOLER_ROWS = [
  '................',
  '.......CC.......',
  '.....CCCCCC.....',
  '...CCCCCCCCCC...',
  '..CCCWCCCCCCCC.C',
  '.CCCCCCCCCCCCCCC',
  '.CCCCCCCCCCCCCC.',
  '..CCCCCCCCCCCC.C',
  '...CCCCCCCCCC...',
  '.....CCCCCC.....',
  '.......CC.......',
  '................',
  '................',
  '................',
  '................',
  '................',
];

const SQUID_ROWS = [
  '......PPPP......',
  '.....PPPPPP.....',
  '....PPPPPPPP....',
  '....PPPPPPPP....',
  '....PPWPPWPP....',
  '....PPPPPPPP....',
  '.....PPPPPP.....',
  '....PPPPPPPP....',
  '...PP.PP.PP.PP..',
  '..PP..PP..PP..P.',
  '..P...PP..PP..P.',
  '.P....PP...P....',
  '......P.........',
  '................',
  '................',
  '................',
];

const ANGLER_ROWS = [
  '.........YYY....',
  '........Y...Y...',
  '.......Y........',
  '.....DDDDDD.....',
  '...DDDDDDDDDD...',
  '..DDDWDDDDDDDD..',
  '.DDDDDDDDDDDDDD.',
  '.DDDDWWWWWWWWDD.',
  '.DDDDDDDDDDDDDD.',
  '..DDDWWWWWWWWDD.',
  '...DDDDDDDDDD...',
  '.....DDDDDD.....',
  '.......DD.......',
  '................',
  '................',
  '................',
];

const MANTIS_ROWS = [
  '....GG..GG......',
  '...G......G.....',
  '....CCCCCCCC....',
  '...CCWCCCCWCC...',
  '..GGGGGGGGGGGG..',
  '..PPPPPPPPPPPP..',
  '...GGGGGGGGGG...',
  '..OO.GGGGGG.OO..',
  '.OO..BBBBBB..OO.',
  '.....BBBBBB.....',
  '....RRRRRRRR....',
  '...RRRR..RRRR...',
  '..TT........TT..',
  '................',
  '................',
  '................',
];

const LEVIATHAN_ROWS = [
  '..GGGGGGGGGGGG..',
  '.GGGGGGGGGGGGGG.',
  'GGGWGGGGGGGGWGGG',
  'GGGGGGGGGGGGGGGG',
  'GGCCCCCCCCCCCCGG',
  '.GGGGGGGGGGGGGG.',
  '..GGGGGGGGGGGG..',
  '...GGGGGGGGGG...',
  '..CCGGGGGGGGCC..',
  '...GGGGGGGGGG...',
  '....GGGGGGGG....',
  '...CCGGGGGGCC...',
  '.....GGGGGG.....',
  '....CC....CC....',
  '................',
  '................',
];

export const BUDDY_SPRITES: Record<BuddyId, PixelSpriteData> = {
  krill: {
    width: 16,
    height: 16,
    rows: KRILL_ROWS,
    palette: { R: '#ff3b6b', P: '#ff8fb1', T: '#ff6b8f', L: '#ffacc5', W: '#ffffff' },
  },
  schooler: {
    width: 16,
    height: 16,
    rows: SCHOOLER_ROWS,
    palette: { C: '#60a5fa', W: '#ffffff' },
  },
  squid: {
    width: 16,
    height: 16,
    rows: SQUID_ROWS,
    palette: { P: '#a855f7', W: '#ffffff' },
  },
  angler: {
    width: 16,
    height: 16,
    rows: ANGLER_ROWS,
    palette: { D: '#334155', Y: '#fde047', W: '#e2e8f0' },
  },
  evil_krill: {
    width: 16,
    height: 16,
    rows: KRILL_ROWS,
    palette: { R: '#dc2626', P: '#991b1b', T: '#ef4444', L: '#fca5a5', W: '#fde047' },
  },
  hackmanite: {
    width: 16,
    height: 16,
    rows: KRILL_ROWS,
    palette: { R: '#c084fc', P: '#e879f9', T: '#a855f7', L: '#f5d0fe', W: '#ffffff' },
  },
  fossil_krill: {
    width: 16,
    height: 16,
    rows: KRILL_ROWS,
    palette: { R: '#cbd5e1', P: '#94a3b8', T: '#e2e8f0', L: '#64748b', W: '#0f172a' },
  },
  mantis_shrimp: {
    width: 16,
    height: 16,
    rows: MANTIS_ROWS,
    palette: {
      G: '#34d399',
      C: '#38bdf8',
      P: '#f472b6',
      O: '#fb923c',
      B: '#818cf8',
      R: '#f43f5e',
      T: '#fde047',
      W: '#ffffff',
    },
  },
  leviathan: {
    width: 16,
    height: 16,
    rows: LEVIATHAN_ROWS,
    palette: { G: '#14b8a6', C: '#fde047', W: '#ffffff' },
  },
};

export const TIER_SPRITES: Record<TierId, PixelSpriteData> = {
  miss: {
    width: 16,
    height: 16,
    rows: [
      '................',
      '.....GGGG.......',
      '...GGGGGGGG.....',
      '.......GGGGGG...',
      '................',
      '..GGGGGGGG......',
      '.....GGGGGGGG...',
      '................',
      '....GGGGGG......',
      '................',
      '................',
      '................',
      '................',
      '................',
      '................',
      '................',
    ],
    palette: { G: '#64748b' },
  },
  plankton: {
    width: 16,
    height: 16,
    rows: [
      '................',
      '....CCC.........',
      '...C...C........',
      '...C.W.C........',
      '....CCC....CC...',
      '..........C..C..',
      '..........C..C..',
      '..CC.......CC...',
      '.C..C...........',
      '..CC.....CCC....',
      '........C.W.C...',
      '........C...C...',
      '.........CCC....',
      '................',
      '................',
      '................',
    ],
    palette: { C: '#93c5fd', W: '#ffffff' },
  },
  tooclever: {
    width: 16,
    height: 16,
    rows: [
      '.......YY.......',
      '.......YY.......',
      '.......YY.......',
      '.......YY.......',
      '.......YY.......',
      '.......YY.......',
      '...Y...YY.......',
      '..YY...YY.......',
      '..YYY..YY.......',
      '...YY..YY.......',
      '....YYYY........',
      '.....YY.........',
      '................',
      '................',
      '................',
      '................',
    ],
    palette: { Y: '#f59e0b' },
  },
  schooler: {
    width: 16,
    height: 16,
    rows: SCHOOLER_ROWS,
    palette: { C: '#38bdf8', W: '#ffffff' },
  },
  rare: {
    width: 16,
    height: 16,
    rows: SQUID_ROWS,
    palette: { P: '#a855f7', W: '#ffffff' },
  },
  deepcut: {
    width: 16,
    height: 16,
    rows: ANGLER_ROWS,
    palette: { D: '#ec4899', Y: '#fde047', W: '#ffffff' },
  },
  krillion: {
    width: 16,
    height: 16,
    rows: KRILL_ROWS,
    palette: { R: '#fde047', P: '#fef08a', T: '#f59e0b', L: '#ffffff', W: '#0f172a' },
  },
};

export const AMBIENT_FISH_SPRITE: PixelSpriteData = {
  width: 16,
  height: 16,
  rows: FISH_ROWS,
  palette: { B: '#071324', W: '#0c1c36' },
};
