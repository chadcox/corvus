import type { ReactNode } from "react";

/**
 * Case-mode navigation rail (plan §4 "Case mode layout" + §5).
 *
 * Pure presentational: it owns no state except what the parent hands it. The
 * active tab, the counts, and the collapsed flag all live in CaseDetailPage so
 * that deep-link/restore behavior stays in one place.
 *
 * Accessible names of the buttons are load-bearing: the e2e suite selects with
 * `getByRole('button', { name: 'Entities', exact: true })`. Icons AND count
 * badges are therefore `aria-hidden` so the name stays exactly the label —
 * counts are decoration here and are stated in full inside each view.
 */

export type CaseTab =
  | "overview"
  | "timeline"
  | "object"
  | "disk"
  | "mft"
  | "browser"
  | "detections"
  | "sources";

export type SeverityLevel = "critical" | "high" | "medium" | "low" | "informational";

type Props = {
  active: CaseTab;
  onSelect: (tab: CaseTab) => void;
  detectionCount: number;
  topSeverity: SeverityLevel | null;
  sourceCount: number;
  hasActiveJob: boolean;
  mftCount: number;
  browserCount: number;
  collapsed: boolean;
  onToggleCollapsed: () => void;
};

type NavItem = {
  tab: CaseTab;
  label: string;
  icon: ReactNode;
  badge?: number;
  badgeSeverity?: SeverityLevel | null;
  dot?: boolean;
};

const S = { width: 14, height: 14, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

const IconOverview = (
  <svg {...S}><rect x="2" y="2" width="5" height="5" /><rect x="9" y="2" width="5" height="5" /><rect x="2" y="9" width="5" height="5" /><rect x="9" y="9" width="5" height="5" /></svg>
);
const IconTimeline = (
  <svg {...S}><circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2.5 1.5" /></svg>
);
const IconEntities = (
  <svg {...S}><path d="M8 1.75l5.25 3v6.5L8 14.25l-5.25-3v-6.5z" /><circle cx="8" cy="8" r="1.75" /></svg>
);
const IconDisk = (
  <svg {...S}><path d="M1.75 4.25h4l1.25 1.5h7.25v7.5H1.75z" /><path d="M1.75 4.25V2.75h3.5" /></svg>
);
const IconMft = (
  <svg {...S}><rect x="1.75" y="2.75" width="12.5" height="10.5" /><path d="M1.75 6.25h12.5M6 6.25v7M1.75 9.75h12.5" /></svg>
);
const IconBrowser = (
  <svg {...S}><circle cx="8" cy="8" r="6.25" /><path d="M1.75 8h12.5M8 1.75c1.75 2 2.6 4 2.6 6.25S9.75 12.25 8 14.25c-1.75-2-2.6-4-2.6-6.25S6.25 3.75 8 1.75z" /></svg>
);
const IconDetections = (
  <svg {...S}><path d="M8 1.75l5 1.75v4.25c0 3-2.1 5.4-5 6.5-2.9-1.1-5-3.5-5-6.5V3.5z" /></svg>
);
const IconSources = (
  <svg {...S}><path d="M1.75 4.25h12.5v9H1.75z" /><path d="M1.75 4.25l1.5-2h9.5l1.5 2M6.25 7.25h3.5" /></svg>
);
const IconCollapse = (
  <svg {...S}><path d="M9.75 4L5.75 8l4 4" /></svg>
);
const IconExpand = (
  <svg {...S}><path d="M6.25 4l4 4-4 4" /></svg>
);

export default function CaseNav({
  active,
  onSelect,
  detectionCount,
  topSeverity,
  sourceCount,
  hasActiveJob,
  mftCount,
  browserCount,
  collapsed,
  onToggleCollapsed,
}: Props) {
  const caseItems: NavItem[] = [
    { tab: "overview", label: "Overview", icon: IconOverview },
    { tab: "timeline", label: "Timeline", icon: IconTimeline },
    { tab: "object", label: "Entities", icon: IconEntities },
    { tab: "disk", label: "Disk", icon: IconDisk },
  ];
  // MFT/Browser are hidden (not disabled) when the evidence has none — dead
  // items are worse than absent ones, and this preserves the current gating.
  if (mftCount > 0) caseItems.push({ tab: "mft", label: "MFT", icon: IconMft });
  if (browserCount > 0) caseItems.push({ tab: "browser", label: "Browser", icon: IconBrowser });
  caseItems.push({
    tab: "detections",
    label: "Detections",
    icon: IconDetections,
    badge: detectionCount,
    badgeSeverity: topSeverity,
  });

  const evidenceItems: NavItem[] = [
    {
      tab: "sources",
      label: "Sources",
      icon: IconSources,
      badge: sourceCount,
      dot: hasActiveJob,
    },
  ];

  const renderItem = (item: NavItem) => {
    const isActive = active === item.tab;
    const showBadge = typeof item.badge === "number" && item.badge > 0;
    const badgeClass = item.badgeSeverity
      ? `nav-badge nav-badge--${item.badgeSeverity}`
      : "nav-badge";
    return (
      <button
        key={item.tab}
        type="button"
        className={`nav-item${isActive ? " active" : ""}`}
        aria-current={isActive ? "page" : undefined}
        title={collapsed ? item.label : undefined}
        onClick={() => onSelect(item.tab)}
      >
        <span className="nav-item-icon" aria-hidden="true">
          {item.icon}
        </span>
        <span className="nav-item-label">{item.label}</span>
        {showBadge && (
          <span className={badgeClass} aria-hidden="true">
            {item.badge! > 999 ? "999+" : item.badge}
          </span>
        )}
        {item.dot && <span className="nav-item-dot" aria-hidden="true" />}
      </button>
    );
  };

  return (
    <nav className={`case-nav${collapsed ? " collapsed" : ""}`} aria-label="Case views">
      <p className="section-label nav-section-label">Case</p>
      <div className="nav-group">{caseItems.map(renderItem)}</div>
      <p className="section-label nav-section-label">Evidence</p>
      <div className="nav-group">{evidenceItems.map(renderItem)}</div>
      <div className="nav-spacer" />
      <button
        type="button"
        className="nav-collapse"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        title={collapsed ? "Expand navigation" : "Collapse navigation"}
      >
        <span className="nav-item-icon" aria-hidden="true">
          {collapsed ? IconExpand : IconCollapse}
        </span>
        <span className="nav-item-label">Collapse</span>
      </button>
    </nav>
  );
}
