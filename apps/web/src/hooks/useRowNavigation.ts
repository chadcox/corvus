import { useCallback, useEffect, useRef, useState } from "react";

type Options = {
  count: number;
  onActivate: (index: number) => void;
  scrollToIndex?: (index: number) => void;
};

export function useRowNavigation<T extends HTMLElement>({
  count,
  onActivate,
  scrollToIndex,
}: Options) {
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<T | null>(null);

  useEffect(() => {
    setActiveIndex((index) => Math.max(0, Math.min(count - 1, index)));
  }, [count]);

  const move = useCallback(
    (next: number) => {
      if (count === 0) return;
      const index = Math.max(0, Math.min(count - 1, next));
      setActiveIndex(index);
      scrollToIndex?.(index);
      requestAnimationFrame(() => {
        containerRef.current
          ?.querySelector<HTMLElement>(`[data-row-index="${index}"]`)
          ?.focus();
      });
    },
    [count, scrollToIndex]
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          move(activeIndex + 1);
          break;
        case "ArrowUp":
          event.preventDefault();
          move(activeIndex - 1);
          break;
        case "Home":
          event.preventDefault();
          move(0);
          break;
        case "End":
          event.preventDefault();
          move(count - 1);
          break;
        case "PageDown":
          event.preventDefault();
          move(activeIndex + 10);
          break;
        case "PageUp":
          event.preventDefault();
          move(activeIndex - 10);
          break;
        case "Enter":
        case " ":
          if (count === 0) return;
          event.preventDefault();
          onActivate(activeIndex);
          break;
      }
    },
    [activeIndex, count, move, onActivate]
  );

  const rowProps = useCallback(
    (index: number) => ({
      "data-row-index": index,
      tabIndex: index === activeIndex ? 0 : -1,
      onFocus: () => setActiveIndex(index),
    }),
    [activeIndex]
  );

  return { containerRef, onKeyDown, rowProps, activeIndex, setActiveIndex };
}
