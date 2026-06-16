import subprocess
from pathlib import Path

from worker.config import settings

# Registry hive basenames (no extension) collected by KAPE
REGISTRY_HIVE_NAMES = frozenset(
    {
        "system",
        "software",
        "sam",
        "security",
        "default",
        "ntuser.dat",
        "usrclass.dat",
    }
)


def _tool_dll(tool_name: str) -> Path | None:
    """Resolve tool DLL; EZ zip layouts nest some tools one level deep."""
    root = Path(settings.eztools_root) / tool_name
    if not root.is_dir():
        return None
    flat = root / f"{tool_name}.dll"
    if flat.is_file():
        return flat
    for dll in root.rglob(f"{tool_name}.dll"):
        if dll.is_file():
            return dll
    return None


def _run_tool_csv(
    tool_name: str,
    input_path: Path,
    output_dir: Path,
    csv_filename: str,
    extra_args: list[str] | None = None,
) -> Path | None:
    dll = _tool_dll(tool_name)
    if dll is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "dotnet",
        str(dll),
        "-f",
        str(input_path),
        "--csv",
        str(output_dir),
        "--csvf",
        csv_filename,
    ]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd, check=False, capture_output=True, timeout=3600)
    csv = output_dir / csv_filename
    return csv if csv.is_file() else None


def _safe_stem(path: Path) -> str:
    name = path.name.replace("$", "").replace("\\", "_") or "artifact"
    return name


def run_evtxecmd(evtx_path: Path, output_dir: Path) -> Path | None:
    return _run_tool_csv("EvtxECmd", evtx_path, output_dir, f"{evtx_path.stem}.csv")


def run_mftecmd(mft_path: Path, output_dir: Path) -> Path | None:
    """Parse raw $MFT export to CSV via MFTECmd."""
    return _run_tool_csv("MFTECmd", mft_path, output_dir, f"{_safe_stem(mft_path)}.csv")


def run_recmd(hive_path: Path, output_dir: Path) -> Path | None:
    """Parse a registry hive to CSV via RECmd."""
    return _run_tool_csv("RECmd", hive_path, output_dir, f"{_safe_stem(hive_path)}.csv")


def run_pecmd(prefetch_path: Path, output_dir: Path) -> Path | None:
    """Parse a prefetch (.pf) file to CSV via PECmd."""
    return _run_tool_csv("PECmd", prefetch_path, output_dir, f"{prefetch_path.stem}.csv", extra_args=["-q"])


def run_amcacheparser(amcache_path: Path, output_dir: Path) -> Path | None:
    """Parse Amcache.hve to CSV via AmcacheParser."""
    return _run_tool_csv("AmcacheParser", amcache_path, output_dir, f"{_safe_stem(amcache_path)}.csv")
