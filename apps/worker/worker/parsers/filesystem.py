from pathlib import Path
from typing import Any

# Corvus scratch directories written during ingest. They are tool output, not
# collected evidence, so they must never appear in the evidence filesystem tree.
SCRATCH_DIR_NAMES = ("_ff_parsed", "_ff_mounted")


def build_filesystem_nodes(
    collection_root: Path,
    evidence_source_id: str,
) -> list[dict[str, Any]]:
    """Build logical filesystem nodes from KAPE raw C\\ collection tree."""
    nodes: list[dict[str, Any]] = []
    if not collection_root.is_dir():
        return nodes

    root_path = collection_root.resolve()

    for path in sorted(root_path.rglob("*")):
        rel = path.relative_to(root_path)
        if any(part in SCRATCH_DIR_NAMES for part in rel.parts):
            continue
        full = "/" + str(rel).replace("\\", "/")
        parent = "/" + str(rel.parent).replace("\\", "/") if rel.parent != Path(".") else None
        if parent == "/.":
            parent = None

        nodes.append(
            {
                "evidence_source_id": evidence_source_id,
                "full_path": full,
                "name": path.name,
                "is_directory": path.is_dir(),
                "size": path.stat().st_size if path.is_file() else None,
                "is_deleted": False,
                "parent_path": parent if parent and parent != "/" else None,
            }
        )
    return nodes
