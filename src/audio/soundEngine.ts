/**
 * Owns Web Audio API retro SFX synthesis and mute state for UI clicks, ticks, and tier fanfares.
 * Does not load external audio files or store settings in localStorage.
 */
import type { TierId } from '../domain/types';

class RetroSoundEngine {
  private ctx: AudioContext | null = null;
  private enabled = true;

  public setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  private ensureContext(): AudioContext | null {
    if (!this.enabled || typeof window === 'undefined') return null;
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioCtx) return null;
    if (!this.ctx) {
      this.ctx = new AudioCtx();
    }
    if (this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  private playTone(
    freq: number,
    durationSec: number,
    type: OscillatorType = 'square',
    gainLevel = 0.06,
    delaySec = 0,
    endFreq?: number
  ): void {
    const ctx = this.ensureContext();
    if (!ctx) return;

    const now = ctx.currentTime + delaySec;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, now);
    if (endFreq !== undefined) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(40, endFreq), now + durationSec);
    }

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(gainLevel, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + durationSec);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + durationSec + 0.02);
  }

  public click(): void {
    this.playTone(540, 0.05, 'square', 0.04, 0, 720);
  }

  public countdownTick(): void {
    this.playTone(440, 0.09, 'triangle', 0.06);
  }

  public countdownGo(): void {
    this.playTone(660, 0.14, 'square', 0.06, 0, 880);
  }

  public urgentTick(): void {
    this.playTone(880, 0.045, 'square', 0.035);
  }

  public thresholdPing(tierIndex: number): void {
    const freqs = [330, 415, 523, 659, 880, 1175];
    const f = freqs[Math.max(0, Math.min(freqs.length - 1, tierIndex))];
    this.playTone(f, 0.11, 'triangle', 0.055, 0, f * 1.15);
  }

  public rejectBuzz(): void {
    this.playTone(170, 0.11, 'sawtooth', 0.055, 0, 120);
    this.playTone(135, 0.12, 'sawtooth', 0.05, 0.08, 95);
  }

  public timeout(): void {
    this.playTone(300, 0.14, 'triangle', 0.06, 0, 180);
    this.playTone(210, 0.22, 'triangle', 0.06, 0.12, 110);
  }

  public acceptTier(tier: TierId): void {
    switch (tier) {
      case 'plankton':
        this.playTone(392, 0.12, 'triangle', 0.06);
        this.playTone(440, 0.16, 'triangle', 0.06, 0.09);
        break;
      case 'tooclever':
        this.playTone(440, 0.1, 'square', 0.045);
        this.playTone(554, 0.16, 'square', 0.045, 0.08);
        break;
      case 'schooler':
        this.playTone(440, 0.09, 'square', 0.05);
        this.playTone(554, 0.09, 'square', 0.05, 0.08);
        this.playTone(659, 0.18, 'square', 0.055, 0.16);
        break;
      case 'rare':
        this.playTone(523, 0.09, 'square', 0.05);
        this.playTone(659, 0.09, 'square', 0.05, 0.08);
        this.playTone(784, 0.1, 'square', 0.055, 0.16);
        this.playTone(1046, 0.22, 'triangle', 0.065, 0.24);
        break;
      case 'deepcut':
        this.playTone(587, 0.08, 'square', 0.05);
        this.playTone(740, 0.08, 'square', 0.05, 0.07);
        this.playTone(880, 0.09, 'square', 0.055, 0.14);
        this.playTone(1174, 0.26, 'square', 0.06, 0.22);
        break;
      case 'krillion':
        this.playTone(523, 0.08, 'square', 0.055, 0);
        this.playTone(659, 0.08, 'square', 0.055, 0.07);
        this.playTone(784, 0.08, 'square', 0.055, 0.14);
        this.playTone(1046, 0.1, 'square', 0.06, 0.21);
        this.playTone(1318, 0.12, 'square', 0.06, 0.29);
        this.playTone(1568, 0.34, 'triangle', 0.07, 0.38);
        break;
      default:
        this.timeout();
    }
  }

  public diveComplete(): void {
    this.playTone(392, 0.1, 'triangle', 0.055, 0);
    this.playTone(494, 0.1, 'triangle', 0.055, 0.09);
    this.playTone(587, 0.12, 'triangle', 0.06, 0.18);
    this.playTone(784, 0.28, 'triangle', 0.065, 0.27);
  }
}

export const soundEngine = new RetroSoundEngine();
