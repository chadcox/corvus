# Open Source Parser Integrations

Corvus uses source adapters to integrate external forensic tools without
making one collector or OS the center of the product.

## Bundling policy

| Tool | License | Status | Use |
|------|---------|--------|-----|
| Plaso / log2timeline | Apache-2.0 | Optional install | Broad timeline extraction for macOS/Linux/generic packages |
| mac_apt | MIT | Optional install | macOS artifact parsing |
| UAC | Apache-2.0 | Import format | Unix-like artifact collection packages |
| Volatility3 | VSL-1.0 | Optional install | Windows memory capture analysis (`.raw`, `.vmem`, `.dmp`, etc.) |
| Velociraptor | AGPL-3.0 | Import only | Collection ZIP/result import; not bundled |
| Plaso (dfVFS/libewf) | Apache-2.0 | Optional install | E01/RAW disk image parsing; reads images directly, no mounting |

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
| `disk_image` | `platform=disk`, `source_type=disk_image`, or disk image file (E01/RAW) | Runs Plaso directly against the image file (read-only); merges generic results for loose files |
| `kape_compat` | KAPE collector or KAPE-shaped Windows package | Existing EZ Tools/Hindsight/Chainsaw path |
| `uac_import` | `collector=uac` or UAC package markers | Imports structured output, then uses Plaso if present or generic fallback |
| `velociraptor_import` | `collector=velociraptor` or Velociraptor collection markers | Imports JSON/JSONL/CSV outputs without bundling Velociraptor |
| `volatility3` | `collector=volatility3` or Windows package with memory image files | Runs selected Volatility3 plugins and imports JSON output |
| `mac_apt` | `platform=macos` or `collector=mac_apt` | Runs/imports mac_apt output; falls back to Plaso/generic |
| `plaso` | macOS/Linux/unknown package when Plaso is installed | Runs `log2timeline.py` and exports JSONL through `psort.py` |
| `generic_directory` | Default | Current parser stack and filesystem indexing |

## Disk image support

Corvus supports E01 (Expert Witness Format), raw DD images, and other common disk image formats:

**Supported formats:**
- E01 (`.e01`, `.e02`, etc.) - Expert Witness Format
- Raw images (`.img`, `.dd`, `.raw`, `.bin`, `.001`)
- AFF format (`.aff`)

**Requirements:**
- Plaso must be installed in the worker image (`INSTALL_OPEN_FORENSICS=true`). Without it the
  adapter still ingests loose files in the package, records a note, and skips image parsing.
- Images are opened read-only by Plaso/dfVFS; Corvus never mounts them, so no FUSE,
  `ewfmount`, or privileged container is required.
- The adapter automatically detects disk images in packages

**Usage:**
1. Upload a ZIP or folder containing a disk image file
2. Optionally include a `manifest.json` with `disk_image_path` and `source_type: "disk_image"`
3. The `disk_image` adapter runs `log2timeline.py` against the image and exports events via `psort.py`
4. Timeline events are generated from the image; filesystem nodes come from loose files in the package

**Example manifest for disk images:**
```json
{
  "package_version": "1",
  "hostname": "WKS-042",
  "source_type": "disk_image",
  "platform": "disk",
  "collector": "ewf",
  "disk_image_path": "E01/DEMO-001.E01",
  "disk_image_size": 10737418240
}
```

External JSON, JSONL, NDJSON, CSV, and TSV outputs are mapped through
`worker.parsers.external_events`, which looks for common timestamp, summary,
artifact, and event-type fields.
