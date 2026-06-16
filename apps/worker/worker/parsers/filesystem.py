from pathlib import Path
from typing import Any


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
