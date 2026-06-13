import { useId } from "react";
import { cn } from "@/lib/utils";

interface SigmXLogoProps {
  className?: string;
}

export function SigmXLogo({ className }: SigmXLogoProps) {
  const gradientId = `sigmx-${useId().replace(/:/g, "")}`;

  return (
    <svg
      viewBox="0 0 48 48"
      role="img"
      aria-label="SigmX logo"
      className={cn("h-6 w-6 shrink-0", className)}
    >
      <defs>
        <linearGradient id={gradientId} x1="8" y1="6" x2="42" y2="42" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset="0.48" stopColor="#34d399" />
          <stop offset="1" stopColor="#f59e0b" />
        </linearGradient>
      </defs>
      <rect
        x="4"
        y="4"
        width="40"
        height="40"
        rx="10"
        fill="#071016"
        stroke={`url(#${gradientId})`}
        strokeWidth="2"
      />
      <path
        d="M30 13H16L26 24L16 35H31"
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M18 28C22 22 27 22 34 28"
        fill="none"
        stroke="#e5f9f6"
        strokeWidth="2.5"
        strokeLinecap="round"
        opacity="0.9"
      />
      <path
        d="M34 15L40 21M40 15L34 21"
        stroke="#f8fafc"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
