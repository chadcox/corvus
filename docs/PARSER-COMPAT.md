# Parser compatibility matrix

Record results from smoke tests on your target server OS.

## v1 required parsers

| Tool | Artifacts | Linux | Windows | Notes |
|------|-----------|-------|---------|-------|
| EvtxECmd | `.evtx` | ✅ | ⬜ | Nested DLL path; run `--sync` for maps |
| MFTECmd | `$MFT`, MFT exports | ✅ | ⬜ | |
| RECmd | Registry hives | ✅ | ⬜ | SYSTEM/SOFTWARE/SAM/etc. |
| AmcacheParser | Amcache | ✅ | ⬜ | `Amcache*.hve` |
| PECmd | Prefetch | ✅ | ⬜ | `.pf` files; `-q` for batch |
| JLECmd | Jump lists | ⬜ | ⬜ | Optional v1 |
| LECmd | `.lnk` | ⬜ | ⬜ | Optional v1 |

Legend: ✅ pass · ❌ fail · ⬜ not tested

## Fallback when a parser fails on Linux

1. Require pre-parsed CSV/JSON output from the collection workflow, **or**
2. Deploy workers on **Windows Server** with native EZ Tools.

## Test commands

See `scripts/smoke-test-eztools.sh` and `scripts/smoke-test-eztools.ps1`.

Update this table after Phase 0 and link the chosen OS in `docs/DEPLOYMENT.md`.
