"""Match Sigma detection blocks against normalized timeline event fields."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Pattern

from worker.sigma.loader import SigmaRule

# EvtxECmd / Windows event field aliases → Sigma field names (lowercase keys)
FIELD_ALIASES: dict[str, str] = {
    "eventid": "eventid",
    "event_id": "eventid",
    "channel": "channel",
    "provider": "provider",
    "computer": "computer",
    "hostname": "computer",
    "machinename": "computer",
    "username": "targetusername",
    "targetusername": "targetusername",
    "subjectusername": "subjectusername",
    "user": "targetusername",
    "processname": "image",
    "image": "image",
    "newprocessname": "newprocessname",
    "parentprocessname": "parentimage",
    "parentimage": "parentimage",
    "commandline": "commandline",
    "parentcommandline": "parentcommandline",
    "logontype": "logontype",
    "ipaddress": "ipaddress",
    "sourceip": "sourceip",
    "destinationip": "destinationip",
    "targetfilename": "targetfilename",
    "objectname": "objectname",
    "recordnumber": "recordnumber",
    "eventrecordid": "eventrecordid",
    "recordid": "recordnumber",
}

LEVEL_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "informational": 0,
}


@dataclass(frozen=True)
class CompiledFieldMatch:
    name: str
    modifier: str | None
    expected: Any


@dataclass(frozen=True)
class CompiledSigmaRule:
    rule: SigmaRule
    condition: str
    selections: dict[str, tuple[CompiledFieldMatch, ...]]
    required_event_ids: frozenset[str]
    service: str
    category: str
    unsupported: bool


def normalize_event_fields(data: dict[str, Any]) -> dict[str, str]:
    """Build lowercase field map for Sigma matching."""
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        canon = FIELD_ALIASES.get(key.lower().replace(" ", ""), key.lower().replace(" ", ""))
        out[canon] = text
        # Sigma often uses EventID as integer string
        if canon == "eventid":
            out["eventid"] = text.split(".")[0]
    return out


def _logsource_matches(rule: SigmaRule, fields: dict[str, str]) -> bool:
    ls = rule.logsource
    service = str(ls.get("service") or "").lower()
    category = str(ls.get("category") or "").lower()
    channel = fields.get("channel", "").lower()

    if service == "security" and channel and "security" not in channel:
        return False
    if service == "system" and channel and "system" not in channel:
        return False
    if service == "application" and channel and "application" not in channel:
        return False
    if category == "process_creation" and fields.get("eventid") not in (
        "4688",
        "1",
        "592",
    ):
        # Still allow if Image/CommandLine present
        if not fields.get("image") and not fields.get("commandline"):
            return False
    return True


def _normalize_expected(expected: Any) -> Any:
    if isinstance(expected, str):
        return expected.lower()
    if isinstance(expected, bool | int):
        return str(expected).lower()
    if isinstance(expected, list):
        return [_normalize_expected(item) for item in expected]
    return str(expected).lower()


def _compile_regex(expected: Any) -> Pattern[str] | None:
    pattern = str(expected if not isinstance(expected, list) else expected[0])
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def _match_modifier(actual: str, modifier: str | None, expected: Any) -> bool:
    actual_l = actual.lower()
    if modifier is None:
        if isinstance(expected, list):
            return any(_match_modifier(actual, None, item) for item in expected)
        return actual_l == _normalize_expected(expected)

    if modifier == "contains":
        parts = expected if isinstance(expected, list) else [_normalize_expected(expected)]
        return any(str(p) in actual_l for p in parts)
    if modifier == "contains|all":
        parts = expected if isinstance(expected, list) else [_normalize_expected(expected)]
        return all(str(p) in actual_l for p in parts)
    if modifier == "startswith":
        parts = expected if isinstance(expected, list) else [_normalize_expected(expected)]
        return any(actual_l.startswith(str(p)) for p in parts)
    if modifier == "endswith":
        parts = expected if isinstance(expected, list) else [_normalize_expected(expected)]
        return any(actual_l.endswith(str(p)) for p in parts)
    if modifier == "re":
        if hasattr(expected, "search"):
            return bool(expected.search(actual))
        compiled = _compile_regex(expected)
        return bool(compiled and compiled.search(actual))
    if modifier == "all":
        parts = expected if isinstance(expected, list) else [_normalize_expected(expected)]
        return all(str(p) in actual_l for p in parts)
    if modifier == "cidr":
        return False
    return False


def _parse_sigma_key(sigma_key: str) -> tuple[str, str | None]:
    if "|" in sigma_key:
        name, modifier = sigma_key.split("|", 1)
    else:
        name, modifier = sigma_key, None
    return name.lower().replace(" ", ""), modifier


def _match_field(fields: dict[str, str], sigma_key: str, expected: Any) -> bool:
    name_l, modifier = _parse_sigma_key(sigma_key)
    actual = fields.get(name_l)
    if actual is None:
        # try without pipe suffix variants
        for fk, fv in fields.items():
            if fk == name_l or fk.endswith(name_l):
                actual = fv
                break
    if actual is None:
        return False
    return _match_modifier(actual, modifier, expected)


def _match_compiled_field(fields: dict[str, str], field: CompiledFieldMatch) -> bool:
    actual = fields.get(field.name)
    if actual is None:
        for fk, fv in fields.items():
            if fk == field.name or fk.endswith(field.name):
                actual = fv
                break
    if actual is None:
        return False
    return _match_modifier(actual, field.modifier, field.expected)


def _selection_matches(selection: dict[str, Any], fields: dict[str, str]) -> bool:
    if not isinstance(selection, dict):
        return False
    for key, expected in selection.items():
        if key == "condition":
            continue
        if not _match_field(fields, str(key), expected):
            return False
    return True


def _compiled_selection_matches(
    selection: tuple[CompiledFieldMatch, ...],
    fields: dict[str, str],
) -> bool:
    return all(_match_compiled_field(fields, field) for field in selection)


def _named_selections(detection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in detection.items():
        if key == "condition":
            continue
        if isinstance(value, dict):
            out[key] = value
    return out


def _eval_compiled_condition(
    condition: str,
    selections: dict[str, tuple[CompiledFieldMatch, ...]],
    fields: dict[str, str],
) -> bool:
    cond = (condition or "selection").strip().lower()

    if cond in selections:
        return _compiled_selection_matches(selections[cond], fields)

    if "1 of" in cond and "*" in cond:
        prefix = cond.replace("1 of", "").strip().replace("*", "").strip()
        return any(
            _compiled_selection_matches(sel, fields)
            for name, sel in selections.items()
            if name.startswith(prefix)
        )

    if "all of" in cond and "*" in cond:
        prefix = cond.replace("all of", "").strip().replace("*", "").strip()
        names = [n for n in selections if n.startswith(prefix)]
        return bool(names) and all(
            _compiled_selection_matches(selections[n], fields) for n in names
        )

    cond_norm = re.sub(r"\s+", " ", cond)

    def eval_atom(atom: str) -> bool:
        atom = atom.strip()
        if not atom:
            return True
        neg = atom.startswith("not ")
        name = atom[4:].strip() if neg else atom
        matched = (
            _compiled_selection_matches(selections[name], fields)
            if name in selections
            else False
        )
        return not matched if neg else matched

    if " or " in cond_norm:
        return any(eval_atom(p) for p in cond_norm.split(" or "))

    if " and " in cond_norm:
        return all(eval_atom(p) for p in cond_norm.split(" and "))

    return eval_atom(cond_norm)


def _eval_condition(condition: str, selections: dict[str, dict[str, Any]], fields: dict[str, str]) -> bool:
    cond = (condition or "selection").strip().lower()

    if cond in selections:
        return _selection_matches(selections[cond], fields)

    if "1 of" in cond and "*" in cond:
        prefix = cond.replace("1 of", "").strip().replace("*", "").strip()
        return any(
            _selection_matches(sel, fields)
            for name, sel in selections.items()
            if name.startswith(prefix)
        )

    if "all of" in cond and "*" in cond:
        prefix = cond.replace("all of", "").strip().replace("*", "").strip()
        names = [n for n in selections if n.startswith(prefix)]
        return bool(names) and all(_selection_matches(selections[n], fields) for n in names)

    # Simple boolean: `a and not b`, `a and b`, `a or b`
    cond_norm = re.sub(r"\s+", " ", cond)

    def eval_atom(atom: str) -> bool:
        atom = atom.strip()
        if not atom:
            return True
        neg = atom.startswith("not ")
        name = atom[4:].strip() if neg else atom
        matched = _selection_matches(selections.get(name, {}), fields) if name in selections else False
        return not matched if neg else matched

    if " or " in cond_norm:
        return any(eval_atom(p) for p in cond_norm.split(" or "))

    if " and " in cond_norm:
        return all(eval_atom(p) for p in cond_norm.split(" and "))

    return eval_atom(cond_norm)


def _compile_expected(modifier: str | None, expected: Any) -> Any:
    if modifier == "re":
        return _compile_regex(expected)
    return _normalize_expected(expected)


def _compile_field(sigma_key: str, expected: Any) -> CompiledFieldMatch:
    name, modifier = _parse_sigma_key(sigma_key)
    return CompiledFieldMatch(
        name=name,
        modifier=modifier,
        expected=_compile_expected(modifier, expected),
    )


def _selection_event_ids(selection: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key, val in selection.items():
        name, modifier = _parse_sigma_key(str(key))
        if name != "eventid" or modifier not in (None,):
            continue
        if isinstance(val, list):
            ids.update(str(v).split(".")[0] for v in val)
        else:
            ids.add(str(val).split(".")[0])
    return ids


def compile_sigma_rule(rule: SigmaRule) -> CompiledSigmaRule | None:
    condition = str(rule.detection.get("condition") or "selection")
    unsupported = any(
        token in condition
        for token in ("|count", "|near", "|fieldref", "timeframe", "keywords:")
    )
    raw_selections = _named_selections(rule.detection)
    if not raw_selections:
        return None

    selections: dict[str, tuple[CompiledFieldMatch, ...]] = {}
    required_ids: set[str] = set()
    for name, selection in raw_selections.items():
        selections[name] = tuple(
            _compile_field(str(key), expected)
            for key, expected in selection.items()
            if key != "condition"
        )
        required_ids.update(_selection_event_ids(selection))

    logsource = rule.logsource
    return CompiledSigmaRule(
        rule=rule,
        condition=condition,
        selections=selections,
        required_event_ids=frozenset(required_ids),
        service=str(logsource.get("service") or "").lower(),
        category=str(logsource.get("category") or "").lower(),
        unsupported=unsupported,
    )


def compile_sigma_rules(rules: list[SigmaRule]) -> list[CompiledSigmaRule]:
    compiled: list[CompiledSigmaRule] = []
    for rule in rules:
        if rule.status == "deprecated":
            continue
        compiled_rule = compile_sigma_rule(rule)
        if compiled_rule:
            compiled.append(compiled_rule)
    return compiled


def compiled_rule_matches_event(rule: CompiledSigmaRule, fields: dict[str, str]) -> bool:
    if not fields:
        return False
    if "eventid" not in fields and "channel" not in fields and "image" not in fields:
        return False
    if rule.unsupported:
        return False
    if rule.required_event_ids and fields.get("eventid") not in rule.required_event_ids:
        return False
    if not _logsource_matches(rule.rule, fields):
        return False

    try:
        return _eval_compiled_condition(rule.condition, rule.selections, fields)
    except Exception:
        return False


def rule_matches_event(rule: SigmaRule, fields: dict[str, str]) -> bool:
    if not fields:
        return False
    if "eventid" not in fields and "channel" not in fields and "image" not in fields:
        # Skip non-Windows-log events (e.g. KAPE CopyLog only)
        return False
    if not _logsource_matches(rule, fields):
        return False

    detection = rule.detection
    condition = str(detection.get("condition") or "selection")
    selections = _named_selections(detection)
    if not selections:
        return False

    unsupported = ("|count", "|near", "|fieldref", "timeframe", "keywords:")
    if any(token in condition for token in unsupported):
        return False

    try:
        return _eval_condition(condition, selections, fields)
    except Exception:
        return False
