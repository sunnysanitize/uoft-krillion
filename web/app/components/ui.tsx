import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Small tracked uppercase caption used for every HUD and section label. */
export function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`text-[11px] uppercase tracking-[0.32em] text-mist ${className}`}>{children}</div>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" };

/**
 * Hard-shadow block button. Pressing it moves the face onto its shadow,
 * so it physically "clicks" without any easing.
 */
export function PixelButton({ variant = "primary", className = "", ...props }: ButtonProps) {
  const look =
    variant === "primary"
      ? "bg-ink text-abyss border-ink hover:bg-white"
      : "bg-deep text-ink border-line hover:border-mist";
  return (
    <button
      {...props}
      className={`font-pixel text-lg uppercase tracking-[0.2em] border-2 px-6 py-3 shadow-block transition-[transform,box-shadow,background-color,border-color] duration-75 active:translate-x-1 active:translate-y-1 active:shadow-none disabled:pointer-events-none disabled:opacity-40 cursor-pointer ${look} ${className}`}
    />
  );
}

/** Square-cornered panel with the block shadow. The one container style in the app. */
export function Panel({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" }) {
  return <Tag className={`border-2 border-line bg-trench/90 shadow-block ${className}`}>{children}</Tag>;
}
