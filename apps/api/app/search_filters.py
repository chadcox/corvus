"""Helpers for building SQL LIKE/ILIKE patterns from analyst-supplied text.

Analyst search terms are literal strings: forensic paths, registry keys, and
command lines routinely contain ``%`` and ``_``, which LIKE would otherwise
treat as wildcards. Unescaped, that both returns wrong results and lets a
single ``%`` query degenerate into a full scan of very large timeline tables.
"""

LIKE_ESCAPE_CHAR = "\\"


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so ``value`` is matched literally.

    Must be paired with ``escape=LIKE_ESCAPE_CHAR`` on the ``like``/``ilike``
    call so the database interprets the escape character the same way.
    """
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )


def like_contains(value: str) -> str:
    """Build a substring LIKE pattern that matches ``value`` literally."""
    return f"%{escape_like(value)}%"
