/**
 * Owns crisp SVG rendering of PixelSpriteData matrices for UI cards and wardrobe slots.
 * Does not define sprite pixel data (see pixelSprites.ts).
 */
import type { PixelSpriteData } from './pixelSprites';

interface PixelSpriteSvgProps {
  sprite: PixelSpriteData;
  size?: number;
  silhouette?: boolean;
  className?: string;
}

export function PixelSpriteSvg({
  sprite,
  size = 48,
  silhouette = false,
  className,
}: PixelSpriteSvgProps) {
  const rects: Array<{ x: number; y: number; fill: string }> = [];
  for (let y = 0; y < sprite.rows.length; y++) {
    const row = sprite.rows[y];
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === '.') continue;
      const color = silhouette ? '#334155' : (sprite.palette[ch] ?? '#ffffff');
      rects.push({ x, y, fill: color });
    }
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${sprite.width} ${sprite.height}`}
      shapeRendering="crispEdges"
      className={className}
      aria-hidden="true"
    >
      {rects.map((r, i) => (
        <rect key={i} x={r.x} y={r.y} width={1} height={1} fill={r.fill} />
      ))}
    </svg>
  );
}
