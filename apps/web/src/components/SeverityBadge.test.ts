import { describe, expect, it } from "vitest";
import { severityAbbrev, severityClass, severityClasses } from "./SeverityBadge";

/**
 * The severity treatment is the one piece of the shell that every view renders
 * (nav rail badges, detections list, summary strip, drawer header). Plan §12
 * requires: canonical modifier class, legacy `sigma-level-*` class kept for the
 * existing CSS and selector-based e2e, and text that carries the level so color
 * is never the only signal.
 *
 * These tests cover the class/label functions. Rendering is covered by the
 * Playwright suite, which is where the CSS cascade actually exists.
 */

const LEVELS = ["critical", "high", "medium", "low", "informational", "info"] as const;

describe("severityClass", () => {
  it("maps each level to its legacy class", () => {
    expect(severityClass("critical")).toBe("sigma-level-critical");
    expect(severityClass("high")).toBe("sigma-level-high");
    expect(severityClass("medium")).toBe("sigma-level-medium");
    expect(severityClass("low")).toBe("sigma-level-low");
  });

  it("folds both spellings of informational onto one class", () => {
    expect(severityClass("informational")).toBe("sigma-level-info");
    expect(severityClass("info")).toBe("sigma-level-info");
  });

  it("normalizes case, because Sigma rules ship mixed-case levels", () => {
    expect(severityClass("CRITICAL")).toBe("sigma-level-critical");
    expect(severityClass("High")).toBe("sigma-level-high");
  });

  it("falls back to medium for unknown, null, or empty levels", () => {
    expect(severityClass("catastrophic")).toBe("sigma-level-medium");
    expect(severityClass(null)).toBe("sigma-level-medium");
    expect(severityClass(undefined)).toBe("sigma-level-medium");
    expect(severityClass("")).toBe("sigma-level-medium");
  });
});

describe("severityClasses", () => {
  it("emits the canonical modifier alongside the legacy class", () => {
    expect(severityClasses("critical")).toBe(
      "severity-badge severity-badge--critical sigma-level-critical"
    );
    expect(severityClasses("low")).toBe("severity-badge severity-badge--low sigma-level-low");
  });

  it("canonicalizes info to informational so one CSS rule covers both", () => {
    expect(severityClasses("info")).toBe(
      "severity-badge severity-badge--informational sigma-level-info"
    );
    expect(severityClasses("informational")).toBe(
      "severity-badge severity-badge--informational sigma-level-info"
    );
  });

  it("falls back to the medium treatment for anything unrecognized", () => {
    expect(severityClasses("bogus")).toBe(
      "severity-badge severity-badge--medium sigma-level-medium"
    );
    expect(severityClasses(null)).toBe("severity-badge severity-badge--medium sigma-level-medium");
  });

  it("always carries the base class plus exactly two modifiers", () => {
    for (const level of [...LEVELS, "bogus", "", null, undefined]) {
      const parts = severityClasses(level).split(" ");
      expect(parts).toHaveLength(3);
      expect(parts[0]).toBe("severity-badge");
      expect(parts[1].startsWith("severity-badge--")).toBe(true);
      expect(parts[2].startsWith("sigma-level-")).toBe(true);
    }
  });
});

describe("severityAbbrev", () => {
  it("uses the four-character abbreviations from the spec", () => {
    expect(severityAbbrev("critical")).toBe("CRIT");
    expect(severityAbbrev("high")).toBe("HIGH");
    expect(severityAbbrev("medium")).toBe("MED");
    expect(severityAbbrev("low")).toBe("LOW");
    expect(severityAbbrev("informational")).toBe("INFO");
    expect(severityAbbrev("info")).toBe("INFO");
  });

  it("normalizes case", () => {
    expect(severityAbbrev("Critical")).toBe("CRIT");
  });

  it("truncates an unknown level rather than blowing out the badge width", () => {
    expect(severityAbbrev("catastrophic")).toBe("CATA");
    expect(severityAbbrev("unknown")).toBe("UNKN");
  });

  it("says N/A when there is no level at all", () => {
    expect(severityAbbrev(null)).toBe("N/A");
    expect(severityAbbrev(undefined)).toBe("N/A");
    expect(severityAbbrev("")).toBe("N/A");
  });

  it("never renders more than four characters", () => {
    for (const level of [...LEVELS, "catastrophic", "moderate", ""]) {
      expect(severityAbbrev(level).length).toBeLessThanOrEqual(4);
    }
  });

  it("keeps text as a non-color signal for every level", () => {
    for (const level of LEVELS) {
      expect(severityAbbrev(level)).not.toBe("");
    }
  });
});
