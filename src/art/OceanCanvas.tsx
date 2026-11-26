/**
 * Owns the full-bleed HTML5 2D ocean backdrop, depth color interpolation, particles, and buddy sprite rendering.
 * Does not manage game timers, scoring, or DOM HUD overlays.
 */
import { useEffect, useRef } from 'react';
import { BUDDY_SPRITES, type PixelSpriteData } from './pixelSprites';
import type { BuddyId } from '../domain/types';

interface OceanCanvasProps {
  targetDepth: number;
  buddyId: BuddyId;
  showBuddy: boolean;
  isDiving: boolean;
  lowPower: boolean;
}

interface Particle {
  x: number;
  y: number;
  r: number;
  speed: number;
  alpha: number;
  isBubble: boolean;
}

interface BgFish {
  x: number;
  y: number;
  speed: number;
  scale: number;
  dir: 1 | -1;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerpColor(c1: [number, number, number], c2: [number, number, number], t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const r = Math.round(lerp(c1[0], c2[0], clamped));
  const g = Math.round(lerp(c1[1], c2[1], clamped));
  const b = Math.round(lerp(c1[2], c2[2], clamped));
  return `rgb(${r}, ${g}, ${b})`;
}

function drawSprite(
  ctx: CanvasRenderingContext2D,
  sprite: PixelSpriteData,
  cx: number,
  cy: number,
  pixelSize: number,
  flipX = false
) {
  const startX = cx - (sprite.width * pixelSize) / 2;
  const startY = cy - (sprite.height * pixelSize) / 2;
  for (let y = 0; y < sprite.rows.length; y++) {
    const row = sprite.rows[y];
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === '.') continue;
      ctx.fillStyle = sprite.palette[ch] ?? '#ffffff';
      const drawX = flipX ? sprite.width - 1 - x : x;
      ctx.fillRect(
        Math.round(startX + drawX * pixelSize),
        Math.round(startY + y * pixelSize),
        Math.ceil(pixelSize),
        Math.ceil(pixelSize)
      );
    }
  }
}

export function OceanCanvas({
  targetDepth,
  buddyId,
  showBuddy,
  isDiving,
  lowPower,
}: OceanCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef({
    targetDepth,
    currentDepth: targetDepth,
    buddyId,
    showBuddy,
    isDiving,
    lowPower,
  });

  stateRef.current.targetDepth = targetDepth;
  stateRef.current.buddyId = buddyId;
  stateRef.current.showBuddy = showBuddy;
  stateRef.current.isDiving = isDiving;
  stateRef.current.lowPower = lowPower;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const particles: Particle[] = Array.from({ length: 42 }, (_, i) => ({
      x: Math.random(),
      y: Math.random(),
      r: 1.5 + (i % 3) * 1.2,
      speed: 0.04 + Math.random() * 0.09,
      alpha: 0.25 + Math.random() * 0.5,
      isBubble: i % 3 === 0,
    }));

    const fishes: BgFish[] = Array.from({ length: 6 }, (_, i) => ({
      x: Math.random(),
      y: 0.35 + (i % 5) * 0.11,
      speed: 0.02 + Math.random() * 0.03,
      scale: 2 + (i % 2),
      dir: i % 2 === 0 ? 1 : -1,
    }));

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    window.addEventListener('resize', resize);

    let rafId = 0;
    let lastTime = performance.now();

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - lastTime) / 1000);
      lastTime = now;

      const s = stateRef.current;
      s.currentDepth = lerp(s.currentDepth, s.targetDepth, Math.min(1, dt * 4.5));
      if (Math.abs(s.currentDepth - s.targetDepth) < 0.2) {
        s.currentDepth = s.targetDepth;
      }

      const w = window.innerWidth;
      const h = window.innerHeight;
      const depth = s.currentDepth;

      // Water colors shift dramatically from 0m to 7000m
      const tTwilight = Math.min(1, depth / 1000);
      const tMidnight = Math.max(0, Math.min(1, (depth - 1000) / 3000));
      const tHadal = Math.max(0, Math.min(1, (depth - 4000) / 3000));

      let topWater = lerpColor([28, 86, 138], [13, 38, 74], tTwilight);
      let botWater = lerpColor([11, 34, 68], [7, 17, 36], tTwilight);
      if (tMidnight > 0) {
        topWater = lerpColor([13, 38, 74], [5, 11, 26], tMidnight);
        botWater = lerpColor([7, 17, 36], [3, 6, 16], tMidnight);
      }
      if (tHadal > 0) {
        topWater = lerpColor([5, 11, 26], [2, 4, 10], tHadal);
        botWater = lerpColor([3, 6, 16], [1, 2, 6], tHadal);
      }

      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, topWater);
      grad.addColorStop(1, botWater);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      // Surface sky and boat visible near depth 0..220m
      const surfaceRatio = Math.max(0, 1 - depth / 260);
      if (surfaceRatio > 0.01) {
        const horizonY = (s.isDiving ? h * 0.14 : h * 0.56) * surfaceRatio - (1 - surfaceRatio) * 80;
        if (horizonY > 0) {
          const skyGrad = ctx.createLinearGradient(0, 0, 0, horizonY);
          skyGrad.addColorStop(0, '#6db7db');
          skyGrad.addColorStop(1, '#d8eef9');
          ctx.fillStyle = skyGrad;
          ctx.fillRect(0, 0, w, horizonY);

          // Sun glow
          const sunX = w * 0.5 + 130;
          const sunY = horizonY * 0.62;
          const sunGrad = ctx.createRadialGradient(sunX, sunY, 8, sunX, sunY, 56);
          sunGrad.addColorStop(0, 'rgba(255, 240, 165, 0.95)');
          sunGrad.addColorStop(0.5, 'rgba(255, 230, 130, 0.35)');
          sunGrad.addColorStop(1, 'rgba(255, 230, 130, 0)');
          ctx.fillStyle = sunGrad;
          ctx.beginPath();
          ctx.arc(sunX, sunY, 56, 0, Math.PI * 2);
          ctx.fill();

          // Pixel clouds
          ctx.fillStyle = 'rgba(255, 255, 255, 0.88)';
          const cloudOffset = s.lowPower ? 0 : ((now * 0.008) % (w + 180)) - 90;
          const drawCloud = (cx: number, cy: number, scale: number) => {
            ctx.fillRect(cx, cy, 48 * scale, 10 * scale);
            ctx.fillRect(cx + 10 * scale, cy - 8 * scale, 26 * scale, 8 * scale);
            ctx.fillRect(cx + 18 * scale, cy - 14 * scale, 14 * scale, 6 * scale);
          };
          drawCloud((w * 0.5 - 160 + cloudOffset * 0.25) % (w + 80) - 40, horizonY * 0.35, 1.1);
          drawCloud(w * 0.5 + 55, horizonY * 0.52, 0.9);

          // Tiny pixel boat on horizon
          const boatX = w * 0.5 - 110;
          const boatBob = s.lowPower ? 0 : Math.sin(now * 0.0025) * 2;
          const by = horizonY - 4 + boatBob;
          ctx.fillStyle = '#0f172a';
          ctx.fillRect(boatX, by, 34, 5);
          ctx.fillRect(boatX + 6, by - 5, 18, 5);
          ctx.fillRect(boatX + 16, by - 16, 2, 11);
          ctx.fillStyle = '#f43f5e';
          ctx.fillRect(boatX + 8, by - 16, 8, 5);

          // Ocean wave line
          ctx.fillStyle = '#1b5080';
          ctx.fillRect(0, horizonY, w, 6);
        }
      }

      // Sunbeams in shallow water
      if (depth < 650 && !s.lowPower) {
        const beamAlpha = Math.max(0, 0.08 * (1 - depth / 650));
        ctx.fillStyle = `rgba(170, 230, 255, ${beamAlpha})`;
        for (let i = 0; i < 4; i++) {
          ctx.beginPath();
          const bx = w * (0.2 + i * 0.2);
          ctx.moveTo(bx, 0);
          ctx.lineTo(bx + 35, 0);
          ctx.lineTo(bx - 80, h);
          ctx.lineTo(bx - 135, h);
          ctx.closePath();
          ctx.fill();
        }
      }

      // Side kelp silhouettes in shallow/twilight waters
      if (depth < 1200) {
        const kelpAlpha = Math.max(0, 0.38 * (1 - depth / 1200));
        ctx.fillStyle = `rgba(6, 18, 36, ${kelpAlpha})`;
        const baseL = Math.max(0, w * 0.5 - 240);
        const baseR = Math.min(w - 28, w * 0.5 + 210);
        for (let k = 0; k < 14; k++) {
          const sway = s.lowPower ? 0 : Math.sin(now * 0.002 + k * 0.6) * 4;
          const yPos = h - k * 24;
          ctx.fillRect(baseL + sway + (k % 2) * 8, yPos, 14, 18);
          ctx.fillRect(baseR - sway - (k % 2) * 6, yPos - 10, 14, 18);
        }
      }

      // Background fish silhouettes
      if (!s.lowPower && depth < 3500) {
        ctx.fillStyle = 'rgba(4, 12, 26, 0.55)';
        for (const f of fishes) {
          f.x += f.speed * f.dir * dt;
          if (f.x > 1.1) f.x = -0.1;
          if (f.x < -0.1) f.x = 1.1;
          const fx = f.x * w;
          const fy = f.y * h;
          ctx.fillRect(fx, fy, 12 * f.scale, 5 * f.scale);
          ctx.fillRect(
            f.dir === 1 ? fx - 4 * f.scale : fx + 12 * f.scale,
            fy - 1 * f.scale,
            4 * f.scale,
            7 * f.scale
          );
        }
      }

      // Bubbles and abyssal motes
      if (!s.lowPower) {
        for (const p of particles) {
          p.y -= p.speed * dt;
          if (p.y < -0.05) {
            p.y = 1.05;
            p.x = Math.random();
          }
          const px = p.x * w;
          const py = p.y * h;
          if (p.isBubble) {
            ctx.strokeStyle =
              depth > 3500
                ? `rgba(56, 214, 255, ${p.alpha * 0.7})`
                : `rgba(210, 240, 255, ${p.alpha * 0.65})`;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.arc(px, py, p.r * 1.4, 0, Math.PI * 2);
            ctx.stroke();
          } else {
            ctx.fillStyle =
              depth > 3000
                ? `rgba(240, 90, 132, ${p.alpha * 0.45})`
                : `rgba(255, 255, 255, ${p.alpha * 0.35})`;
            ctx.fillRect(px, py, p.r, p.r);
          }
        }
      }

      // Equipped Dive Buddy sprite
      if (s.showBuddy) {
        const sprite = BUDDY_SPRITES[s.buddyId] ?? BUDDY_SPRITES.krill;
        const buddyX = s.isDiving ? Math.max(54, w * 0.5 - 145) : Math.max(60, w * 0.5 - 125);
        const bob = s.lowPower ? 0 : Math.sin(now * 0.004) * 5;
        const buddyY = (s.isDiving ? h * 0.72 : h * 0.49) + bob;
        drawSprite(ctx, sprite, buddyX, buddyY, 2.8);
      }

      rafId = window.requestAnimationFrame(frame);
    };

    rafId = window.requestAnimationFrame(frame);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  );
}
