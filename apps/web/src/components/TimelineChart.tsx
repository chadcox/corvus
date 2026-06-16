import { useEffect, useMemo, useRef, useState } from "react";
import { TimelineHistogram } from "../api/client";

type Props = {
  histogram: TimelineHistogram;
  detectionHistogram?: TimelineHistogram | null;
  /** Called with ISO start/end strings when the user clicks a bucket */
  onBucketClick?: (start: string, end: string) => void;
};

const LABEL_H = 18;
const BAR_W_MIN = 6;
const BAR_W_MAX = 56;
const GAP = 2;
const MIN_BAR_H = 4;

function bucketLabel(ts: string, granularity: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "";
  if (granularity === "minute" || granularity === "hour") {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { month: "numeric", day: "numeric", year: "2-digit" });
}

function bucketTitle(ts: string, count: number, granularity: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return `${count} events`;
  const label = granularity === "minute" || granularity === "hour"
    ? d.toLocaleString()
    : d.toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
  return `${label}\n${count.toLocaleString()} event${count === 1 ? "" : "s"}`;
}

export default function TimelineChart({ histogram, detectionHistogram, onBucketClick }: Props) {
  const { buckets, total, granularity } = histogram;
  const [hovered, setHovered] = useState<number | null>(null);
  const [scrollHeight, setScrollHeight] = useState(220);
  const [scrollWidth, setScrollWidth] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const maxCount = useMemo(
    () => Math.max(1, ...buckets.map((b) => b.count)),
    [buckets]
  );

  const barW = useMemo(() => {
    if (!buckets.length || scrollWidth <= 0) return 9;
    return Math.max(
      BAR_W_MIN,
      Math.min(BAR_W_MAX, Math.floor((scrollWidth - GAP * (buckets.length - 1)) / buckets.length))
    );
  }, [buckets.length, scrollWidth]);
  const unit = barW + GAP;
  const labelEvery = Math.max(1, Math.ceil(96 / unit));
  const viewW = buckets.length * unit - GAP;
  const detectionCounts = useMemo(() => {
    const map = new Map<string, number>();
    detectionHistogram?.buckets.forEach((b) => map.set(b.ts, b.count));
    return map;
  }, [detectionHistogram]);

  if (!buckets.length) return null;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => {
      setScrollHeight(Math.max(110, Math.floor(el.clientHeight)));
      setScrollWidth(Math.max(0, Math.floor(el.clientWidth)));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const barArea = Math.max(80, scrollHeight - LABEL_H);
  const svgHeight = barArea + LABEL_H;
  const hovBucket = hovered !== null ? buckets[hovered] : null;

  return (
    <div className="tl-chart">
      <div className="tl-chart-header">
        <span className="tl-chart-meta">
          {total.toLocaleString()} events · {granularity === "minute" ? "minute" : granularity === "hour" ? "hourly" : granularity === "day" ? "daily" : granularity === "week" ? "weekly" : "monthly"} distribution
        </span>
        {detectionHistogram && detectionHistogram.total > 0 && (
          <span className="tl-chart-legend">
            <span className="tl-chart-legend-dot" aria-hidden="true" />
            {detectionHistogram.total.toLocaleString()} detections overlaid
          </span>
        )}
        {/* Always rendered to prevent layout shift; opacity toggled via class */}
        <span className={`tl-chart-hover-label${hovBucket ? " tl-chart-hover-label--visible" : ""}`}>
          {hovBucket ? bucketTitle(hovBucket.ts, hovBucket.count, granularity) : " "}
        </span>
      </div>
      <div ref={scrollRef} className="tl-chart-scroll">
        <svg
          width={viewW}
          height={svgHeight}
          className="tl-chart-svg"
          aria-label="Event density chart"
          role="img"
        >
          {buckets.map((b, i) => {
            // Use sqrt scaling so low/mid buckets remain visible when a few
            // buckets dominate the case volume.
            const normalized = b.count / maxCount;
            const barH = Math.max(MIN_BAR_H, Math.round(Math.sqrt(normalized) * barArea));
            const x = i * unit;
            const isHov = hovered === i;
            const intensity = 0.25 + 0.75 * (b.count / maxCount);
            const nextTs = buckets[i + 1]?.ts ?? b.ts;
            const detectionCount = detectionCounts.get(b.ts) ?? 0;

            return (
              <g key={b.ts + i}>
                <rect
                  x={x}
                  y={barArea - barH}
                  width={barW}
                  height={barH}
                  rx={1}
                  fill={isHov ? "var(--accent)" : "var(--text-soft)"}
                  opacity={isHov ? 1 : intensity}
                  style={{ cursor: onBucketClick ? "pointer" : "default", transition: "opacity 0.1s" }}
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onBucketClick?.(b.ts, nextTs)}
                >
                  <title>{bucketTitle(b.ts, b.count, granularity)}</title>
                </rect>
                {detectionCount > 0 && (
                  <rect
                    x={x}
                    y={Math.max(0, barArea - barH - 5)}
                    width={barW}
                    height={3}
                    rx={1}
                    fill="var(--critical)"
                    opacity={isHov ? 1 : 0.9}
                    style={{ pointerEvents: "none" }}
                  >
                    <title>{`${detectionCount.toLocaleString()} detection event${detectionCount === 1 ? "" : "s"}`}</title>
                  </rect>
                )}
                {i % labelEvery === 0 && (
                  <text
                    x={x + barW / 2}
                    y={barArea + 14}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={600}
                    fontFamily="var(--font-mono)"
                    fill="var(--text-soft)"
                    style={{ pointerEvents: "none" }}
                  >
                    {bucketLabel(b.ts, granularity)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {onBucketClick && (
        <p className="tl-chart-hint">Click a bar to filter to that time window</p>
      )}
    </div>
  );
}
