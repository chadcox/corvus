import { ReactNode, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { useDialog } from "../hooks/useDialog";

/**
 * Right-hand overlay drawer (plan §7.2): secondary context that overlays the
 * workspace without losing your place — source info, ingest history, container
 * logs.
 *
 * Focus trap, Escape handling, scroll lock, `inert` on #root and focus return
 * all come from `useDialog`, the same hook the existing modals use. Rendered
 * through a portal so the drawer is never clipped by a `ResizableSplit` or a
 * scrolled view container.
 */

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** CSS width of the panel. Default 420px per §7.2. */
  width?: string;
  /** Optional actions rendered in the header, left of the close button. */
  actions?: ReactNode;
};

export default function Drawer({ open, onClose, title, children, width = "420px", actions }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useDialog(open, panelRef, onClose);

  if (!open) return null;

  return createPortal(
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className="drawer-panel"
        style={{ width }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-head">
          <h2 id={titleId} className="drawer-title">
            {title}
          </h2>
          <div className="drawer-head-actions">
            {actions}
            <button type="button" className="secondary drawer-close" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>,
    document.body
  );
}
