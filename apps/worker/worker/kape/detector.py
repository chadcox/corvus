from dataclasses import dataclass, field
from pathlib import Path

from corvus_core.constants import KapeCategory, KAPE_LOG_CSV_HINTS, KAPE_MODULE_CSV_HINTS
from worker.eztools.runner import REGISTRY_HIVE_NAMES
from worker.hindsight.profiles import find_browser_profiles


@dataclass
class KapeLayout:
    root: Path
    raw_collection: Path | None = None
    category_dirs: dict[str, Path] = field(default_factory=dict)
    csv_files: list[Path] = field(default_factory=list)
    evtx_files: list[Path] = field(default_factory=list)
    mft_files: list[Path] = field(default_factory=list)
    registry_hives: list[Path] = field(default_factory=list)
    prefetch_files: list[Path] = field(default_factory=list)
    amcache_files: list[Path] = field(default_factory=list)
    browser_profile_dirs: list[Path] = field(default_factory=list)


def _find_raw_collection(root: Path) -> Path | None:
    for name in ("C", "c"):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def _is_registry_hive(path: Path) -> bool:
    return path.name.lower() in REGISTRY_HIVE_NAMES


def _is_amcache_hive(path: Path) -> bool:
    lower = path.name.lower()
    return lower.startswith("amcache") and lower.endswith(".hve")


def detect_kape_layout(package_dir: Path) -> KapeLayout:
    """Detect KAPE-style output under package root (or nested single folder)."""
    root = package_dir
    children = [p for p in root.iterdir() if p.is_dir() and p.name not in (".git", "__MACOSX")]
    if len(children) == 1 and not (root / "manifest.json").is_file():
        nested = children[0]
        if _find_raw_collection(nested) or any(
            (nested / cat.value).is_dir() for cat in KapeCategory if cat != KapeCategory.RAW_COLLECTION
        ):
            root = nested

    layout = KapeLayout(root=root, raw_collection=_find_raw_collection(root))

    for cat in KapeCategory:
        if cat == KapeCategory.RAW_COLLECTION:
            continue
        path = root / cat.value
        if path.is_dir():
            layout.category_dirs[cat.value] = path

    for path in root.rglob("*"):
        if "_ff_parsed" in path.parts:
            continue
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith(".csv") and any(h.lower() in lower for h in KAPE_MODULE_CSV_HINTS):
            layout.csv_files.append(path)
        elif lower.endswith(".csv") and any(h.lower() in lower for h in KAPE_LOG_CSV_HINTS):
            layout.csv_files.append(path)
        elif lower.endswith(".csv") and path.parent.name in layout.category_dirs:
            layout.csv_files.append(path)
        elif lower.endswith(".evtx"):
            layout.evtx_files.append(path)
        elif lower in ("$mft", "mft") or lower.endswith("_mft") or lower.endswith(".mft"):
            layout.mft_files.append(path)
        elif lower.endswith(".pf"):
            layout.prefetch_files.append(path)
        elif _is_amcache_hive(path):
            layout.amcache_files.append(path)
        elif _is_registry_hive(path):
            layout.registry_hives.append(path)

    layout.browser_profile_dirs = find_browser_profiles(root)
    return layout
