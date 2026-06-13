import { useMemo } from "react";
import { DISCLAIMER_WATERMARK } from "@/lib/disclaimer";

/**
 * Full-page tiled watermark overlay.
 *
 * Two stacked layers — one for light theme (black ink), one for dark (white
 * ink) — toggled via Tailwind's ``dark:`` variant. Only the active-theme
 * layer is visible. Both are non-interactive (``pointer-events-none``) and
 * sit at ``z-30``: above page content, below modals/toasts (z-50) so dialogs
 * stay clear. Placed inside Layout, so login/register pages (outside Layout)
 * are not watermarked.
 */

function buildBg(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="160" viewBox="0 0 320 160">
  <g transform="rotate(-20 160 80)">
    <text x="160" y="86" text-anchor="middle"
      font-family="Inter, 'Microsoft YaHei', sans-serif"
      font-size="15" font-weight="600" fill="${color}">${DISCLAIMER_WATERMARK}</text>
  </g>
</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

const TILE = "320px 160px";

export function Watermark() {
  const lightBg = useMemo(() => buildBg("#000000"), []);
  const darkBg = useMemo(() => buildBg("#ffffff"), []);
  const style = { backgroundSize: TILE, backgroundRepeat: "repeat" } as const;
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-30">
      {/* Light theme */}
      <div
        className="absolute inset-0 opacity-[0.05] dark:hidden"
        style={{ ...style, backgroundImage: lightBg }}
      />
      {/* Dark theme */}
      <div
        className="absolute inset-0 hidden opacity-[0.06] dark:block"
        style={{ ...style, backgroundImage: darkBg }}
      />
    </div>
  );
}
