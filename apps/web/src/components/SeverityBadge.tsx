/**
 * One severity treatment for the whole app (plan §12).
 *
 * Emits three classes per badge:
 *   - `severity-badge` + `severity-badge--<level>` — the canonical §12 spec
 *     (11px 600 mono, 1px severity border, `*-dim` background). These rules sit
 *     later in App.css than the legacy ones, so they win.
 *   - the legacy `sigma-level-*` class — kept because existing CSS and
 *     selector-based tests reference it, per §12 "keep class names".
 *
 * Color is never the only signal — the abbreviation text carries the level, and
 * `title`/`aria-label` spell it out in full for assistive tech.
 */

/** Legacy class kept for compatibility (informational maps to `-info`). */
const LEVEL_CLASS: Record<string, string> = {
  critical: "sigma-level-critical",
  high: "sigma-level-high",
  medium: "sigma-level-medium",
  low: "sigma-level-low",
  informational: "sigma-level-info",
  info: "sigma-level-info",
};

const LEVEL_ABBREV: Record<string, string> = {
  critical: "CRIT",
  high: "HIGH",
  medium: "MED",
  low: "LOW",
  informational: "INFO",
  info: "INFO",
};

const CANONICAL: Record<string, string> = {
  critical: "critical",
  high: "high",
  medium: "medium",
  low: "low",
  informational: "informational",
  info: "informational",
};

/** Legacy `sigma-level-*` class for a level; unknown levels fall back to medium. */
export function severityClass(level: string | null | undefined): string {
  return LEVEL_CLASS[(level ?? "").toLowerCase()] ?? "sigma-level-medium";
}

/** §12 row treatment: 2px left edge in the severity color (critical also fills). */
export function severityRowClass(level: string | null | undefined): string {
  const canonical = CANONICAL[(level ?? "").toLowerCase()] ?? "medium";
  return `severity-row--${canonical}`;
}

/** Full class list for a §12 badge: canonical modifier + legacy class. */
export function severityClasses(level: string | null | undefined): string {
  const canonical = CANONICAL[(level ?? "").toLowerCase()] ?? "medium";
  return `severity-badge severity-badge--${canonical} ${severityClass(level)}`;
}

export function severityAbbrev(level: string | null | undefined): string {
  const key = (level ?? "").toLowerCase();
  return LEVEL_ABBREV[key] ?? (key ? key.slice(0, 4).toUpperCase() : "N/A");
}

type Props = {
  level: string | null | undefined;
  /** Extra context appended to the accessible label (e.g. the rule title). */
  title?: string;
  /** `abbrev` (default) shows CRIT/HIGH/MED/LOW/INFO; `full` shows the raw level. */
  variant?: "abbrev" | "full";
  className?: string;
};

export default function SeverityBadge({ level, title, variant = "abbrev", className }: Props) {
  const raw = (level ?? "").toLowerCase() || "unknown";
  const text = variant === "full" ? raw : severityAbbrev(level);
  const label = title ? `${raw} severity: ${title}` : `${raw} severity`;
  return (
    <span
      className={`status-badge ${severityClasses(level)}${className ? ` ${className}` : ""}`}
      title={label}
      aria-label={label}
    >
      {text}
    </span>
  );
}
