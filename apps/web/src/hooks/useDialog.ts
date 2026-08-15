import { RefObject, useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function useDialog(
  open: boolean,
  dialogRef: RefObject<HTMLElement | null>,
  onClose: () => void
) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;

    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const appRoot = document.getElementById("root");
    const rootWasInert = appRoot?.inert ?? false;
    const bodyOverflow = document.body.style.overflow;
    if (appRoot) appRoot.inert = true;
    document.body.style.overflow = "hidden";

    const frame = requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      (dialog?.querySelector<HTMLElement>(FOCUSABLE) ?? dialog)?.focus();
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const dialog = dialogRef.current;
      if (!dialog) return;
      const items = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.offsetParent !== null
      );
      if (items.length === 0) {
        event.preventDefault();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = bodyOverflow;
      if (appRoot) appRoot.inert = rootWasInert;
      if (opener?.isConnected) opener.focus();
    };
  }, [dialogRef, open]);
}
