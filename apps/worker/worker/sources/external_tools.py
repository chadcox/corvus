from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import subprocess
from pathlib import Path

from worker.config import settings


def tool_available(path_or_name: str) -> bool:
    if not path_or_name:
        return False
    candidate = Path(path_or_name)
    if candidate.is_file():
        return True
    return shutil.which(path_or_name) is not None


def run_command(args: list[str], *, timeout: int, cwd: Path | None = None) -> tuple[bool, str | None]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode != 0:
        # plaso emits informative logs before the actual failure line;
        # keep the tail so we preserve the root-cause message.
        msg = (result.stderr or result.stdout or "").strip()
        if not msg:
            return False, f"exit code {result.returncode}"
        return False, msg[-1000:]
    return True, None


def plaso_available() -> bool:
    return tool_available(settings.plaso_log2timeline_bin) and tool_available(settings.plaso_psort_bin)


def _plaso_parsers_for_platform(platform: str) -> str:
    target = (platform or "").lower()
    if target == "macos":
        return settings.plaso_macos_parsers
    if target == "linux":
        return settings.plaso_linux_parsers
    return settings.plaso_unknown_parsers


def _plaso_family_spec_for_platform(platform: str) -> str:
    target = (platform or "").lower()
    if target == "macos":
        return settings.plaso_macos_families
    if target == "linux":
        return settings.plaso_linux_families
    return settings.plaso_unknown_families


def _parse_plaso_families(spec: str) -> list[tuple[str, str]]:
    families: list[tuple[str, str]] = []
    for part in (spec or "").split(";"):
        raw = part.strip()
        if not raw:
            continue
        if "=" in raw:
            name, parsers = raw.split("=", 1)
            label = name.strip() or "family"
            parser_list = parsers.strip()
        else:
            label = "family"
            parser_list = raw
        if parser_list:
            families.append((label, parser_list))
    return families


def _run_plaso_family(
    package_dir: Path,
    output_dir: Path,
    *,
    label: str,
    parsers: str,
) -> tuple[Path | None, str | None]:
    storage = output_dir / f"timeline-{label}.plaso"
    jsonl = output_dir / f"plaso-{label}.jsonl"
    ok, err = run_command(
        [
            settings.plaso_log2timeline_bin,
            "--status_view",
            "none",
            "--storage-file",
            str(storage),
            "--workers",
            str(settings.plaso_workers),
            "--parsers",
            parsers,
            str(package_dir),
        ],
        timeout=settings.plaso_timeout_seconds,
    )
    if not ok:
        return None, f"{label}: {err}"
    ok, err = run_command(
        [
            settings.plaso_psort_bin,
            "--status_view",
            "none",
            "-o",
            "json_line",
            "-w",
            str(jsonl),
            str(storage),
        ],
        timeout=settings.plaso_timeout_seconds,
    )
    if not ok:
        return None, f"{label}: {err}"
    return jsonl, None


def run_plaso(package_dir: Path, output_dir: Path, *, platform: str) -> tuple[Path | None, str | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl = output_dir / "plaso.jsonl"
    if settings.plaso_parallel_enabled:
        families = _parse_plaso_families(_plaso_family_spec_for_platform(platform))
        if len(families) >= 2:
            max_jobs = max(1, settings.plaso_parallel_jobs)
            outputs: dict[str, Path] = {}
            errors: list[str] = []
            with ThreadPoolExecutor(max_workers=max_jobs) as pool:
                futures = {
                    pool.submit(
                        _run_plaso_family,
                        package_dir,
                        output_dir,
                        label=label,
                        parsers=parsers,
                    ): label
                    for label, parsers in families
                }
                for future in as_completed(futures):
                    out, err = future.result()
                    label = futures[future]
                    if out:
                        outputs[label] = out
                    elif err:
                        errors.append(err)
            merged_parts = [outputs[label] for label, _ in families if label in outputs]
            if not merged_parts:
                return None, " | ".join(errors)[:1000] if errors else "Plaso produced no outputs"
            with jsonl.open("w", encoding="utf-8") as merged:
                for part in merged_parts:
                    with part.open("r", encoding="utf-8", errors="replace") as src:
                        shutil.copyfileobj(src, merged)
            return jsonl, None

    single_label = "full"
    single_parsers = _plaso_parsers_for_platform(platform)
    out, err = _run_plaso_family(
        package_dir,
        output_dir,
        label=single_label,
        parsers=single_parsers,
    )
    if not out:
        return None, err
    with out.open("r", encoding="utf-8", errors="replace") as src, jsonl.open("w", encoding="utf-8") as merged:
        shutil.copyfileobj(src, merged)
    return jsonl, None


def mac_apt_available() -> bool:
    return tool_available(settings.mac_apt_bin)


def run_mac_apt(package_dir: Path, output_dir: Path) -> tuple[Path | None, str | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ok, err = run_command(
        [
            settings.mac_apt_bin,
            "MOUNTED",
            str(package_dir),
            str(output_dir),
        ],
        timeout=settings.mac_apt_timeout_seconds,
    )
    return (output_dir if ok else None), err


def volatility3_available() -> bool:
    return tool_available(settings.volatility3_bin)


def run_volatility3(
    memory_image: Path,
    output_dir: Path,
    *,
    plugins: list[str],
) -> tuple[Path | None, str | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    ran_any = False
    for plugin in plugins:
        plugin_name = plugin.strip()
        if not plugin_name:
            continue
        ran_any = True
        output_path = output_dir / f"{plugin_name.replace('.', '_')}.json"
        try:
            result = subprocess.run(
                [
                    settings.volatility3_bin,
                    "-q",
                    "-f",
                    str(memory_image),
                    "-r",
                    "json",
                    plugin_name,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=settings.volatility3_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{plugin_name}: {exc}")
            continue
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
            errors.append(f"{plugin_name}: {msg[-1000:]}")
            continue
        output_path.write_text(result.stdout or "[]", encoding="utf-8")
    if not ran_any:
        return None, "No Volatility3 plugins configured"
    if not any(output_dir.glob("*.json")):
        return None, " | ".join(errors)[:1000] if errors else "Volatility3 produced no outputs"
    return output_dir, (" | ".join(errors)[:1000] if errors else None)


def run_volatility3_banners(memory_image: Path) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            [
                settings.volatility3_bin,
                "-q",
                "-f",
                str(memory_image),
                "banners.Banners",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=settings.volatility3_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        return None, msg[-1000:]
    return (result.stdout or ""), None
