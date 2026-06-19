# Evidence Package Format

## Overview

Analysts upload a folder or ZIP containing endpoint evidence from Windows, macOS, or Linux systems. Corvus detects the package layout, selects a source adapter, ingests pre-parsed tool output when present, and optionally runs supported parsers against raw collected files.

KAPE packages are supported and can be uploaded directly. The format below is intentionally generic so other collectors and source adapters can produce equivalent packages.

## Recommended layout

```text
WKS-042_20250528/
  manifest.json          # recommended
  C/                     # raw target collection (optional)
    Windows/
      System32/
        ...
  EvidenceOfExecution/   # parser/module output (category folders vary)
  Registry/
  EventLogs/
  ...
```

## manifest.json

```json
{
  "package_version": "1",
  "hostname": "WKS-042",
  "collected_at": "2025-05-28T14:00:00Z",
  "collector": "endpoint-collector",
  "collector_version": "1.0.0",
  "source_type": "endpoint",
  "platform": "windows",
  "os_version": "Windows 11 23H2",
  "architecture": "x86_64",
  "modules_run": ["EvtxECmd", "MFTECmd"],
  "timezone": "America/New_York"
}
```

If omitted, hostname is inferred from the folder name and known collector layouts are detected heuristically.

## Ingest priority

1. **Module CSV/JSON** — EvtxECmd, MFTECmd, PECmd, RECmd, AmcacheParser, etc.
2. **Raw artifacts** — `.evtx`, registry hives, prefetch, `$MFT` when unparsed
3. **Collected files only** — filesystem nodes from paths and timestamps

## Field workflow

1. Collect endpoint evidence and, when possible, include parser CSV/JSON output.
2. Copy or ZIP the output directory.
3. Create case in Corvus → upload package.
4. Monitor ingest job → review Timeline / Object / Disk views.

## Supported package families

| Family | Notes |
|--------|-------|
| Generic directory/ZIP | Baseline support for raw artifacts, CSV/JSON parser output, browser profiles, and filesystem paths |
| KAPE-compatible | Supported as one Windows package shape |
| UAC | Unix-like Artifacts Collector packages are imported and parsed with available adapters |
| Velociraptor | Collection exports are import-compatible; Velociraptor itself is not bundled |
| mac_apt | Existing or generated mac_apt CSV/JSONL output is mapped into the timeline |
| Plaso | `log2timeline.py`/`psort.py` output is mapped into the timeline when Plaso is installed |
