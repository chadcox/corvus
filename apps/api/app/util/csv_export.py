"""CSV formula-injection mitigation for analyst-facing exports.

Evidence text is attacker-controlled: an intruder can name a file or emit a log
message that begins with ``=``, ``+``, ``-``, or ``@``. Spreadsheet software
treats such a cell as a formula, so opening an exported report can execute
content authored by the subject of the investigation (CSV/formula injection,
OWASP "CSV Injection").

A per-cell prefix alone is not enough: the writer emits comma-delimited rows,
but spreadsheets in many locales import CSV with a semicolon (or tab) list
separator. An unquoted cell such as ``safe;=cmd`` is one logical field here and
two cells there, and the second one starts a formula. Exports therefore quote
every field, which bounds each logical value across any delimiter a spreadsheet
might use.

Escaping happens only at the CSV serialization boundary. Stored rows, JSON API
responses, and worker COPY serialization keep the original bytes so evidence
fidelity is preserved.
"""

from __future__ import annotations

import csv
import re
from typing import IO, Any

# Leading characters a spreadsheet may interpret as the start of a formula.
# The full-width forms are included because spreadsheet input normalization can
# fold them back to their ASCII equivalents.
FORMULA_PREFIXES = ("=", "+", "-", "@", "＝", "＋", "－", "＠")
# Leading whitespace controls that let a formula prefix slip past naive checks.
CONTROL_PREFIXES = ("\t", "\r", "\n")

# Plain numbers are left alone so ordinary negative values stay readable.
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

ESCAPE_PREFIX = "'"


def is_formula_like(value: str) -> bool:
    """Return True when a spreadsheet could parse ``value`` as a formula."""
    if not value:
        return False
    if value.startswith(CONTROL_PREFIXES):
        return True
    if not value.startswith(FORMULA_PREFIXES):
        return False
    return not _NUMERIC_RE.match(value)


def escape_csv_cell(value: object, *, enabled: bool = True) -> object:
    """Neutralize one CSV cell, leaving non-text and safe values untouched."""
    if not enabled or not isinstance(value, str):
        return value
    if not is_formula_like(value):
        return value
    return ESCAPE_PREFIX + value


def escape_csv_row(values: list[object], *, enabled: bool = True) -> list[object]:
    """Neutralize every cell in a CSV data row."""
    if not enabled:
        return values
    return [escape_csv_cell(v, enabled=True) for v in values]


def csv_writer(buffer: IO[str], *, enabled: bool = True) -> Any:
    """Build the writer used by analyst exports.

    Quoting every field keeps each logical value bounded when a spreadsheet
    imports the file with a non-comma list separator, so an embedded delimiter
    cannot split a cell open in front of an escaped formula prefix. With
    escaping disabled the writer falls back to plain minimal quoting.
    """
    quoting = csv.QUOTE_ALL if enabled else csv.QUOTE_MINIMAL
    return csv.writer(buffer, quoting=quoting)
