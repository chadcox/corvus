# Open Source Parser Integrations

ForensicFlow uses source adapters to integrate external forensic tools without
making one collector or OS the center of the product.

## Bundling policy

| Tool | License | Status | Use |
|------|---------|--------|-----|
| Plaso / log2timeline | Apache-2.0 | Optional install | Broad timeline extraction for macOS/Linux/generic packages |
| mac_apt | MIT | Optional install | macOS artifact parsing |
| UAC | Apache-2.0 | Import format | Unix-like artifact collection packages |
| Volatility3 | VSL-1.0 | Optional install | Windows memory capture analysis (`.raw`, `.vmem`, `.dmp`, etc.) |
| Velociraptor | AGPL-3.0 | Import only | Collection ZIP/result import; not bundled |

Permissive tools may be installed into the worker image with:

```bash
INSTALL_OPEN_FORENSICS=true docker compose up -d --build
```

```bash
INSTALL_OPEN_FORENSICS=true \
INSTALL_VOLATILITY3=true \
docker compose up -d --build
```

## Adapter behavior

| Adapter | Selection | Behavior |
|---------|-----------|----------|
| `kape_compat` | KAPE collector or KAPE-shaped Windows package | Existing EZ Tools/Hindsight/Chainsaw path |
| `uac_import` | `collector=uac` or UAC package markers | Imports structured output, then uses Plaso if present or generic fallback |
| `velociraptor_import` | `collector=velociraptor` or Velociraptor collection markers | Imports JSON/JSONL/CSV outputs without bundling Velociraptor |
| `volatility3` | `collector=volatility3` or Windows package with memory image files | Runs selected Volatility3 plugins and imports JSON output |
| `mac_apt` | `platform=macos` or `collector=mac_apt` | Runs/imports mac_apt output; falls back to Plaso/generic |
| `plaso` | macOS/Linux/unknown package when Plaso is installed | Runs `log2timeline.py` and exports JSONL through `psort.py` |
| `generic_directory` | Default | Current parser stack and filesystem indexing |

External JSON, JSONL, NDJSON, CSV, and TSV outputs are mapped through
`worker.parsers.external_events`, which looks for common timestamp, summary,
artifact, and event-type fields.
