import { useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";

type Props = {
  left: ReactNode;
  right: ReactNode;
  defaultLeftPct?: number;
  minLeftPct?: number;
  maxLeftPct?: number;
  className?: string;
};

export default function ResizableSplit({
  left,
  right,
  defaultLeftPct = 62,
  minLeftPct = 35,
  maxLeftPct = 75,
  className = "",
}: Props) {
  const [splitPct, setSplitPct] = useState(defaultLeftPct);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  const updateSplitFromClientX = (clientX: number) => {
    const host = hostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    if (rect.width <= 0) return;
    const raw = ((clientX - rect.left) / rect.width) * 100;
    const clamped = Math.max(minLeftPct, Math.min(maxLeftPct, raw));
    setSplitPct(clamped);
  };

  const onSplitMouseDown = (e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    draggingRef.current = true;
    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      updateSplitFromClientX(ev.clientX);
    };
    const onUp = () => {
      draggingRef.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div
      ref={hostRef}
      className={`resizable-split ${className}`.trim()}
      style={{ ["--split-left" as string]: `${splitPct}%` }}
    >
      {left}
      <div
        className="timeline-splitter"
        role="separator"
        aria-label="Resize main and detail panels"
        aria-orientation="vertical"
        aria-valuemin={minLeftPct}
        aria-valuemax={maxLeftPct}
        aria-valuenow={Math.round(splitPct)}
        tabIndex={0}
        onMouseDown={onSplitMouseDown}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setSplitPct((p) => Math.max(minLeftPct, p - 2));
          if (e.key === "ArrowRight") setSplitPct((p) => Math.min(maxLeftPct, p + 2));
        }}
      />
      {right}
    </div>
  );
}
