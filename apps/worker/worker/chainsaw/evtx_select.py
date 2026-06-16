"""Select high-value EVTX files for Chainsaw hunt (IR-focused)."""

from __future__ import annotations

from pathlib import Path

# Lower rank = hunted first. Filename / path substring match (case-insensitive).
_PRIORITY_PATTERNS: tuple[tuple[int, str], ...] = (
    (0, "security.evtx"),
    (1, "microsoft-windows-sysmon"),
    (1, "sysmon"),
    (2, "powershell"),
    (2, "windows-powershell"),
    (3, "terminalservices"),
    (3, "remoteconnection"),
    (4, "taskscheduler"),
    (4, "microsoft-windows-wmi-activity"),
    (5, "winrm"),
    (5, "microsoft-windows-winrm"),
    (6, "microsoft-windows-smbclient"),
    (6, "smbclient"),
    (7, "microsoft-windows-dns-client"),
    (7, "dns-client"),
    (8, "microsoft-windows-lsa"),
    (9, "microsoft-windows-bits-client"),
    (10, "microsoft-windows-windows defender"),
    (10, "windows defender"),
)


def evtx_priority_rank(path: Path) -> int:
    """Return sort rank for an EVTX path; 999 = low priority / other."""
    text = f"{path.parent.name}/{path.name}".lower()
    best = 999
    for rank, pattern in _PRIORITY_PATTERNS:
        if pattern in text:
            best = min(best, rank)
    return best


def is_priority_evtx(path: Path) -> bool:
    return evtx_priority_rank(path) < 999


def find_evtx_files(
    package_dir: Path,
    *,
    max_files: int = 64,
    mode: str = "priority",
) -> list[Path]:
    """
    Collect EVTX paths for Chainsaw hunt.

    mode ``priority`` (default): IR-relevant logs first, then others up to max_files.
    mode ``all``: lexicographic order, capped at max_files.
    """
    all_evtx = [p for p in package_dir.rglob("*.evtx") if p.is_file()]
    if not all_evtx:
        return []

    mode = (mode or "priority").lower()
    if mode == "all":
        return sorted(all_evtx)[:max_files]

    ranked = sorted(all_evtx, key=lambda p: (evtx_priority_rank(p), str(p).lower()))
    priority = [p for p in ranked if is_priority_evtx(p)]
    if len(priority) >= max_files:
        return priority[:max_files]
    remainder = [p for p in ranked if not is_priority_evtx(p)]
    return (priority + remainder)[:max_files]
