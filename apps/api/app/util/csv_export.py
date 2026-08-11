"""CSV formula-injection mitigation for analyst-facing exports.

Evidence text is attacker-controlled: an intruder can name a file or emit a log
message that begins with ``=``, ``+``, ``-``, or ``@``. Spreadsheet software
treats such a cell as a formula, so opening an exported report can execute
content authored by the subject of the investigation (CSV/formula injection,
OWASP "CSV Injection").

A per-cell prefix alone is not enough: the writer emits comma-delimited rows,
but importing that stream with a semicolon or tab delimiter can expose a later
part of an attacker-controlled value as a new cell. Formula initiators are
therefore escaped both at the start of a value and after delimiters or line
boundaries that can produce such derived cells. Canonical output remains
comma-delimited and quotes every field while protection is enabled.

Escaping happens only at the CSV serialization boundary. Stored rows, JSON API
responses, and worker COPY serialization keep the original bytes so evidence
fidelity is preserved.
"""

from __future__ import annotations

import csv
from typing import IO, Any

# Leading characters a spreadsheet may interpret as the start of a formula.
# The full-width forms are included because spreadsheet input normalization can
# fold them back to their ASCII equivalents.
FORMULA_PREFIXES = ("=", "+", "-", "@", "＝", "＋", "－", "＠")
# Leading whitespace controls that let a formula prefix slip past naive checks.
CONTROL_PREFIXES = ("\t", "\r", "\n")

ESCAPE_PREFIX = "'"


def _is_plain_number(value: str) -> bool:
    """Recognize the top-level numeric exception without regex backtracking."""
    length = len(value)
    index = 1 if value.startswith(("+", "-")) else 0
    if index == length:
        return False

    integer_start = index
    while index < length and "0" <= value[index] <= "9":
        index += 1
    has_digits = index > integer_start

    if index < length and value[index] == ".":
        index += 1
        fraction_start = index
        while index < length and "0" <= value[index] <= "9":
            index += 1
        has_digits = has_digits or index > fraction_start

    if not has_digits:
        return False

    if index < length and value[index] in ("e", "E"):
        index += 1
        if index < length and value[index] in ("+", "-"):
            index += 1
        exponent_start = index
        while index < length and "0" <= value[index] <= "9":
            index += 1
        if index == exponent_start:
            return False

    return index == length


def is_formula_like(value: str) -> bool:
    """Return True when a spreadsheet could parse ``value`` as a formula."""
    if not value:
        return False
    if value.startswith(CONTROL_PREFIXES):
        return True
    if not value.startswith(FORMULA_PREFIXES):
        return False
    return not _is_plain_number(value)


def _boundary_length(value: str, index: int) -> int:
    """Return the delimiter length at ``index``, treating CRLF atomically."""
    char = value[index]
    if char == "\r":
        return 2 if index + 1 < len(value) and value[index + 1] == "\n" else 1
    if char in (";", "\t", "\n"):
        return 1
    return 0


def escape_csv_cell(value: object, *, enabled: bool = True) -> object:
    """Neutralize formula-like starts in one CSV value in a single pass."""
    if not enabled or not isinstance(value, str):
        return value
    if not value:
        return value

    escaped: list[str] = []
    index = 0
    at_value_start = True
    top_level = True
    top_level_number = _is_plain_number(value)

    while index < len(value):
        char = value[index]
        if at_value_start and (
            char in CONTROL_PREFIXES
            or (char in FORMULA_PREFIXES and not (top_level and top_level_number))
        ):
            escaped.append(ESCAPE_PREFIX)

        boundary_length = _boundary_length(value, index)
        if boundary_length:
            escaped.append(value[index : index + boundary_length])
            index += boundary_length
            at_value_start = True
            top_level = False
            continue

        if at_value_start and not top_level and char == '"':
            # The canonical writer doubles embedded quotes. Alternate-delimiter
            # parsers can consume that quote run, so it does not end the derived
            # cell's formula-sensitive start state.
            escaped.append(char)
            index += 1
            continue

        escaped.append(char)
        index += 1
        at_value_start = False

    return "".join(escaped)


def escape_csv_row(values: list[object], *, enabled: bool = True) -> list[object]:
    """Neutralize every cell in a CSV data row."""
    if not enabled:
        return values
    return [escape_csv_cell(v, enabled=True) for v in values]


def csv_writer(buffer: IO[str], *, enabled: bool = True) -> Any:
    """Build the writer used by analyst exports.

    The canonical format is comma CSV. All fields remain quoted when protection
    is enabled; alternate-delimiter safety comes from ``escape_csv_cell``, not
    from assuming those parsers preserve comma-column boundaries. With escaping
    disabled the writer falls back to plain minimal quoting.
    """
    quoting = csv.QUOTE_ALL if enabled else csv.QUOTE_MINIMAL
    return csv.writer(buffer, quoting=quoting)
