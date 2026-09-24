"""The 7-step onboarding interview (spec section 6.4): steps, fields, parsing.

Every answer is stored in brain.json `onboarding.answers.<field>` as
{value, quote, at, runtime, session, verified}. The quote is the operator's
verbatim words; this module never invents one. Values from CLI flags carry
the literal flag text as their quote and runtime "cli"; defaults filled by
`init --non-interactive` carry an empty quote and runtime "default".
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import state

MODES = ("personal", "agency", "organisation")
PRESETS = {"startup": "organisation", "solo-consultant": "agency"}
MODE_ALIASES = {
    "a": "personal", "me": "personal", "just me": "personal", "personal": "personal",
    "b": "agency", "agency": "agency", "firm": "agency",
    "c": "organisation", "org": "organisation", "organisation": "organisation",
    "organization": "organisation", "company": "organisation",
}
DEFAULT_AREAS = ["work", "home", "relationships", "learning", "health", "money"]
PRIVATE_AREAS = ("health", "money")

QUESTIONS = {
    1: "Who is this brain for? (a) just me: personal, (b) my firm, serving outside clients: agency, "
       "(c) an organisation with a team and roles: organisation. More than one is fine.",
    2: "Do you want a preset? agency: solo-consultant or none; organisation: startup or none.",
    3: "What is your name and how should I address you? Keep my name as Tess or pick another. "
       "Your timezone looks like {tz}: is that right?",
    4: "Besides you, whose words count as decisions here, and for what? (for example a co-founder "
       "for everything, or a client owner for one client). Everyone else's words are recorded as facts.",
    5: "{entities}",
    6: "How should I keep conversation journals? commit-redacted (default), stub-only (bodies stay "
       "local) or local. Health and money areas are always private. Anything I read is sent to this "
       "runtime's model provider, including .private/.",
    7: "Private git remote URL (or 'later')? Push automatically after save (yes/no)? Which CLIs do "
       "you use (claude, codex, gemini, kimi)?",
}
ENTITY_QUESTIONS = {
    "agency": "Agency: its name, one line on what you sell, and up to 3 clients.",
    "organisation": "Organisation: its name, your seat, up to 5 seats or units, and do you serve "
                    "outside clients?",
    "personal": "Personal: which areas (work, home, relationships, learning, health*, money*; "
                "* = private) and up to 3 active projects?",
}

FIELD_STEP = {
    "mode": 1, "preset": 2, "operator_name": 3, "assistant_name": 3, "timezone": 3,
    "address_as": 3, "principals": 4, "agency_name": 5, "agency_offer": 5, "clients": 5,
    "org_name": 5, "operator_seat": 5, "seats": 5, "units": 5, "serves_clients": 5,
    "areas": 5, "projects": 5, "journal": 6, "remote_url": 7, "autopush": 7, "runtimes": 7,
}
LIST_FIELDS = ("clients", "seats", "units", "areas", "projects", "runtimes")
BOOL_FIELDS = ("serves_clients", "autopush")
MODE_FIELDS = {
    "agency": ("agency_name", "agency_offer", "clients"),
    "organisation": ("org_name", "operator_seat", "seats", "units", "serves_clients"),
    "personal": ("areas", "projects"),
}
OPTIONAL = ("address_as",)


def modes_of(brain: Dict[str, Any]) -> List[str]:
    ans = (brain.get("onboarding") or {}).get("answers") or {}
    value = (ans.get("mode") or {}).get("value")
    if isinstance(value, list) and value:
        return value
    return list(brain.get("modes") or [])


def required_fields(step: int, brain: Dict[str, Any]) -> List[str]:
    if step == 5:
        out: List[str] = []
        for mode in modes_of(brain) or ["personal"]:
            out.extend(MODE_FIELDS.get(mode, ()))
        return out
    return [f for f, s in FIELD_STEP.items() if s == step and f not in OPTIONAL and f not in _all_mode_fields()]


def _all_mode_fields() -> List[str]:
    return [f for fields in MODE_FIELDS.values() for f in fields]


def answered(brain: Dict[str, Any]) -> Dict[str, Any]:
    return (brain.get("onboarding") or {}).get("answers") or {}


def next_step(brain: Dict[str, Any]) -> int:
    ans = answered(brain)
    for step in range(1, state.TOTAL_STEPS + 1):
        if any(f not in ans for f in required_fields(step, brain)):
            return step
    return state.TOTAL_STEPS


def all_answered(brain: Dict[str, Any]) -> bool:
    ans = answered(brain)
    return all(f in ans for s in range(1, state.TOTAL_STEPS + 1) for f in required_fields(s, brain))


def question_for(step: int, brain: Dict[str, Any]) -> str:
    if step == 5:
        return " ".join(ENTITY_QUESTIONS[m] for m in (modes_of(brain) or ["personal"]))
    return QUESTIONS[step].format(tz=brain.get("timezone") or state.detect_timezone(), entities="")


# ------------------------------------------------------------- parsing ------

def _as_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw).strip()
        if text.lower() in ("", "none", "no", "skip", "-"):
            return []
        if text.startswith("["):
            try:
                items = json.loads(text)
            except ValueError:
                raise state.BrainError("could not parse list value: %s" % text)
        else:
            items = [p for p in text.replace(";", ",").split(",")]
    return [str(i).strip() for i in items if str(i).strip()]


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("y", "yes", "true", "1", "on"):
        return True
    if text in ("n", "no", "false", "0", "off", "later"):
        return False
    raise state.BrainError("expected yes/no, got %r" % raw)


def parse_modes(raw: Any) -> List[str]:
    out: List[str] = []
    for item in _as_list(raw.replace("+", ",") if isinstance(raw, str) else raw):
        mode = MODE_ALIASES.get(item.lower())
        if mode is None:
            raise state.BrainError("unknown mode %r (personal, agency, organisation)" % item)
        if mode not in out:
            out.append(mode)
    if not out:
        raise state.BrainError("at least one mode is required")
    return out


def parse_principals(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        items = raw
    else:
        text = raw if isinstance(raw, str) else json.dumps(raw)
        if text.strip().startswith("["):
            items = json.loads(text)
        else:
            items = []
            for part in _as_list(text):
                name, _, scope = part.partition(":")
                items.append({"name": name.strip(), "scope": scope.strip() or "**"})
    out = []
    for item in items:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            raise state.BrainError("each principal needs a name")
        scope = item.get("scope", "**")
        scopes = scope if isinstance(scope, list) else [s.strip() for s in str(scope).split("|") if s.strip()]
        out.append({"name": str(item["name"]).strip(), "scope": scopes or ["**"],
                    "decides": bool(item.get("decides", True)), "role": item.get("role", "principal")})
    return out


def parse_value(field: str, raw: Any, brain: Dict[str, Any]) -> Any:
    if field == "mode":
        return parse_modes(raw)
    if field == "principals":
        return parse_principals(raw)
    if field in LIST_FIELDS:
        return _as_list(raw)
    if field in BOOL_FIELDS:
        return _as_bool(raw)
    text = str(raw).strip()
    if field == "preset":
        return _parse_preset(text, brain)
    if field == "journal" and text not in state.JOURNAL_POLICIES:
        raise state.BrainError("journal must be one of %s" % ", ".join(state.JOURNAL_POLICIES))
    if field == "timezone" and not state.valid_timezone(text):
        raise state.BrainError("unknown timezone %r (use an IANA name like Europe/Lisbon)" % text)
    if field == "remote_url" and text.lower() in ("", "later", "none", "no"):
        return None
    if not text and field in ("operator_name", "agency_name", "org_name"):
        raise state.BrainError("%s cannot be empty" % field)
    return text


def _parse_preset(text: str, brain: Dict[str, Any]) -> Optional[str]:
    if text.lower() in ("", "none", "no", "skip"):
        return None
    if text not in PRESETS:
        raise state.BrainError("unknown preset %r (%s, or none)" % (text, ", ".join(PRESETS)))
    base = PRESETS[text]
    if base not in modes_of(brain):
        raise state.BrainError("preset %s needs mode %s" % (text, base))
    return text


# ----------------------------------------------------------- recording ------

def record(brain: Dict[str, Any], field: str, raw: Any, quote: str, runtime: str = "",
           session: str = "", at: str = "") -> Dict[str, Any]:
    """Store one answer. Re-answering a field overwrites it (same step)."""
    if field not in FIELD_STEP:
        raise state.BrainError("unknown field %r; fields: %s" % (field, ", ".join(sorted(FIELD_STEP))))
    if runtime not in ("default",) and not str(quote).strip():
        raise state.BrainError("--quote is required: the operator's verbatim words for this answer")
    value = parse_value(field, raw, brain)
    onb = brain.setdefault("onboarding", {})
    entry = {"value": value, "quote": str(quote), "at": at or state.now_iso(brain.get("timezone")),
             "runtime": runtime, "session": session, "verified": False}
    onb.setdefault("answers", {})[field] = entry
    if field == "mode":
        brain["modes"] = value
        brain["primary_mode"] = value[0]
    if field == "preset":
        brain["presets"] = [value] if value else []
    if onb.get("status") in (None, "pending", "deferred"):
        onb["status"] = "in_progress"
        onb["remind_after"] = None
    if not onb.get("started_at"):
        onb["started_at"] = entry["at"]
    onb["step"] = next_step(brain)
    return entry


def default_for(field: str, brain: Dict[str, Any]) -> Any:
    """The value `init --non-interactive` fills when no answer was given."""
    ident = brain.get("identity") or {}
    modes = modes_of(brain)
    table = {
        "preset": "none", "assistant_name": ident.get("assistant_name") or "Tess",
        "operator_name": ident.get("operator_name") or "", "timezone": brain.get("timezone") or "UTC",
        "principals": "none", "agency_name": "Agency", "agency_offer": "", "clients": [],
        "org_name": "Organisation", "operator_seat": "lead", "seats": [], "units": [],
        "serves_clients": False, "areas": list(DEFAULT_AREAS), "projects": [],
        "journal": "stub-only" if "organisation" in modes else "commit-redacted",
        "remote_url": "later", "autopush": False, "runtimes": ["claude-code", "codex", "gemini"],
    }
    if field not in table:
        raise state.BrainError("no default for %s; it must be answered" % field)
    return table[field]


def fill_defaults(brain: Dict[str, Any], until_step: int) -> List[str]:
    filled = []
    for step in range(1, until_step + 1):
        for field in required_fields(step, brain):
            if field in answered(brain):
                continue
            value = default_for(field, brain)
            if field == "operator_name" and not value:
                raise state.BrainError("operator name unknown: pass --operator NAME")
            record(brain, field, value, "", runtime="default")
            filled.append(field)
    return filled
