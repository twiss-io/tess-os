"""Read-only validation for the advisory adapter-manifest records.

This module deliberately does not import ``tessctl`` or a provider SDK.  It
only reads a caller-supplied source tree, parses the local engine as Python
AST, and returns descriptive findings.  The results are not a gate, approval,
or conformance certificate.
"""

from __future__ import annotations

import ast
import errno
import io
import json
import os
import stat
import tokenize
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


MANIFEST_DIRECTORY = Path("adapters/manifests")
SCHEMA_PATH = Path("adapters/contracts/adapter-manifest.schema.json")
ENGINE_PATH = Path(".tess/bin/tessctl")

MANIFEST_NAMES: Tuple[str, ...] = (
    "claude-code.adapter-manifest.json",
    "codex.adapter-manifest.json",
    "generic.adapter-manifest.json",
    "perplexity.adapter-manifest.json",
)

EXPECTED_CLAIMS: Dict[str, Dict[str, Any]] = {
    "claude-code": {
        "manifest": "claude-code.adapter-manifest.json",
        "support_level": "C3",
        "status": "preview",
        "capabilities": {
            "instruction-rendering",
            "prompt-artifacts",
            "config-fragment",
            "local-process-driver",
        },
        "render_target": "claude-code",
        "driver": "claude",
    },
    "codex": {
        "manifest": "codex.adapter-manifest.json",
        "support_level": "C2",
        "status": "preview",
        "capabilities": {
            "instruction-rendering",
            "prompt-artifacts",
            "config-fragment",
            "local-process-driver",
        },
        "render_target": "codex",
        "driver": "codex",
    },
    "generic": {
        "manifest": "generic.adapter-manifest.json",
        "support_level": "C2",
        "status": "preview",
        "capabilities": {"instruction-rendering", "prompt-artifacts"},
        "render_target": "generic",
        "driver": None,
    },
    "perplexity": {
        "manifest": "perplexity.adapter-manifest.json",
        "support_level": "C0",
        "status": "not-supported",
        "capabilities": set(),
        "render_target": None,
        "driver": None,
    },
}

_REQUIRED_FIELDS = {
    "schema_version",
    "adapter_id",
    "provider",
    "support_level",
    "status",
    "capabilities",
    "evidence",
    "limits",
}
_EVIDENCE_FIELDS = {"kind", "path", "note"}
_ALLOWED_EVIDENCE_KINDS = {"repository-source", "status-page"}
_ALLOWED_CAPABILITIES = {
    "instruction-rendering",
    "prompt-artifacts",
    "config-fragment",
    "local-process-driver",
    "read-only-research",
}
_FORBIDDEN_TERMS = (
    "authority",
    "access",
    "approval",
    "sign",
    "key",
    "verifier",
    "trust",
    "protected",
)


class _StrictJsonError(ValueError):
    """Raised when local JSON is malformed or contains duplicate keys."""


def _reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError("duplicate object key {!r}".format(key))
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise _StrictJsonError("non-finite JSON constant {!r}".format(value))


def _open_root(root: Path, findings: List[str]) -> Optional[int]:
    """Open the supplied repository root without following its final symlink."""
    # ``Path.absolute()`` may resolve a final symlink on some platforms;
    # ``abspath`` makes a lexical absolute path so O_NOFOLLOW sees it.
    candidate = Path(os.path.abspath(str(root)))
    if not hasattr(os, "O_NOFOLLOW"):
        findings.append("root: this platform cannot safely open advisory inputs without following symlinks")
        return None
    try:
        descriptor = os.open(str(candidate), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            findings.append("root: repository root must not be a symlink")
        else:
            findings.append("root: cannot open repository root: {}".format(exc))
        return None
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        findings.append("root: repository root must be a directory")
        os.close(descriptor)
        return None
    return descriptor


def _relative_parts(relative: Path, label: str, findings: List[str]) -> Optional[Tuple[str, ...]]:
    if relative.is_absolute() or ".." in relative.parts:
        findings.append("{}: must be a traversal-free repository-relative path".format(label))
        return None
    parts = relative.parts
    if not parts:
        findings.append("{}: path must name a regular file".format(label))
        return None
    for part in parts:
        if part in ("", ".", ".."):
            findings.append("{}: path contains an unsafe component".format(label))
            return None
    return tuple(parts)


def _open_relative(
    root_fd: int, relative: Path, label: str, findings: List[str], expect_directory: bool
) -> Optional[int]:
    """Open an in-tree regular file/directory through no-follow descriptors.

    Every component is opened relative to an already-open parent descriptor.
    That prevents a post-check replacement from changing the object ultimately
    read or enumerated.
    """
    parts = _relative_parts(relative, label, findings)
    if parts is None:
        return None
    current = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            final = index == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if not final or expect_directory:
                flags |= os.O_DIRECTORY
            try:
                opened = os.open(part, flags, dir_fd=current)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    findings.append("{}: symlinks are not allowed".format(label))
                else:
                    findings.append("{}: cannot safely open input: {}".format(label, exc))
                return None
            os.close(current)
            current = opened
            mode = os.fstat(current).st_mode
            if final:
                allowed = stat.S_ISDIR(mode) if expect_directory else stat.S_ISREG(mode)
                if not allowed:
                    noun = "directory" if expect_directory else "regular file"
                    findings.append("{}: must be an existing {}".format(label, noun))
                    return None
            elif not stat.S_ISDIR(mode):
                findings.append("{}: parent component is not a directory".format(label))
                return None
        result = current
        current = -1
        return result
    finally:
        if current >= 0:
            os.close(current)


def _read_descriptor(descriptor: int, label: str, findings: List[str]) -> Optional[str]:
    """Read a regular descriptor without reopening its pathname."""
    chunks: List[bytes] = []
    try:
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append("{}: cannot read UTF-8 input: {}".format(label, exc))
        return None


def _strict_json_descriptor(descriptor: int, label: str, findings: List[str]) -> Optional[Any]:
    text = _read_descriptor(descriptor, label, findings)
    if text is None:
        return None
    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_nonfinite
        )
    except (json.JSONDecodeError, _StrictJsonError) as exc:
        findings.append("{}: strict JSON parse failed: {}".format(label, exc))
        return None


def _is_forbidden(value: str) -> bool:
    lower = value.lower()
    return any(term in lower for term in _FORBIDDEN_TERMS)


def _validate_evidence(root_fd: int, evidence: Any, label: str, findings: List[str]) -> None:
    if not isinstance(evidence, list) or not evidence:
        findings.append("{}.evidence: must be a non-empty array".format(label))
        return
    for index, item in enumerate(evidence):
        item_label = "{}.evidence[{}]".format(label, index)
        if not isinstance(item, dict):
            findings.append("{}: must be an object".format(item_label))
            continue
        unknown = sorted(set(item) - _EVIDENCE_FIELDS)
        missing = sorted(_EVIDENCE_FIELDS - set(item))
        for field in missing:
            findings.append("{}: missing required field {!r}".format(item_label, field))
        for field in unknown:
            findings.append("{}: field {!r} is not allowed".format(item_label, field))
        kind = item.get("kind")
        if kind not in _ALLOWED_EVIDENCE_KINDS:
            findings.append("{}.kind: must be one of {}".format(item_label, sorted(_ALLOWED_EVIDENCE_KINDS)))
        note = item.get("note")
        if not isinstance(note, str) or not note:
            findings.append("{}.note: must be a non-empty string".format(item_label))
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            findings.append("{}.path: must be a non-empty string".format(item_label))
            continue
        windows_path = PureWindowsPath(raw_path)
        relative = Path(raw_path)
        if (
            relative.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or "\\" in raw_path
            or ".." in relative.parts
            or ".." in windows_path.parts
        ):
            findings.append(
                "{}.path: must be a traversal-free repository-relative path".format(item_label)
            )
            continue
        descriptor = _open_relative(
            root_fd, relative, "{}.path".format(item_label), findings, expect_directory=False
        )
        if descriptor is not None:
            os.close(descriptor)


def _validate_manifest(
    root_fd: int, manifest_name: str, data: Any, findings: List[str]
) -> None:
    label = "adapters/manifests/{}".format(manifest_name)
    if not isinstance(data, dict):
        findings.append("{}: top-level JSON value must be an object".format(label))
        return

    unknown = sorted(set(data) - _REQUIRED_FIELDS)
    missing = sorted(_REQUIRED_FIELDS - set(data))
    for field in missing:
        findings.append("{}: missing required field {!r}".format(label, field))
    for field in unknown:
        if _is_forbidden(field):
            findings.append("{}: authority-bearing field {!r} is not allowed".format(label, field))
        else:
            findings.append("{}: field {!r} is not allowed".format(label, field))

    if data.get("schema_version") != "tess.adapter-manifest.v1":
        findings.append("{}.schema_version: must equal 'tess.adapter-manifest.v1'".format(label))

    adapter_id = data.get("adapter_id")
    expected = EXPECTED_CLAIMS.get(adapter_id) if isinstance(adapter_id, str) else None
    if expected is None:
        findings.append("{}.adapter_id: {!r} is not allowlisted".format(label, adapter_id))
    elif expected["manifest"] != manifest_name:
        findings.append("{}.adapter_id: does not match canonical filename".format(label))

    provider = data.get("provider")
    if not isinstance(provider, str) or not provider:
        findings.append("{}.provider: must be a non-empty string".format(label))

    support_level = data.get("support_level")
    if support_level not in {"C0", "C1", "C2", "C3"}:
        findings.append("{}.support_level: C4 and unknown levels are not allowed".format(label))

    status = data.get("status")
    if status not in {"not-supported", "preview"}:
        findings.append("{}.status: must be 'not-supported' or 'preview'".format(label))

    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        findings.append("{}.capabilities: must be an array".format(label))
    else:
        if len(set(item for item in capabilities if isinstance(item, str))) != len(capabilities):
            findings.append("{}.capabilities: duplicate or non-string capability values are not allowed".format(label))
        for capability in capabilities:
            if not isinstance(capability, str):
                findings.append("{}.capabilities: values must be strings".format(label))
            elif _is_forbidden(capability):
                findings.append("{}.capabilities: authority-bearing capability {!r} is not allowed".format(label, capability))
            elif capability not in _ALLOWED_CAPABILITIES:
                findings.append("{}.capabilities: capability {!r} is not allowed".format(label, capability))

    _validate_evidence(root_fd, data.get("evidence"), label, findings)

    limits = data.get("limits")
    if not isinstance(limits, list) or not limits:
        findings.append("{}.limits: must be a non-empty array".format(label))
    elif any(not isinstance(item, str) or not item for item in limits):
        findings.append("{}.limits: values must be non-empty strings".format(label))

    if expected is None:
        return
    for field in ("support_level", "status"):
        if data.get(field) != expected[field]:
            findings.append(
                "{}.{}: expected {!r} for {!r}".format(
                    label, field, expected[field], adapter_id
                )
            )
    if isinstance(capabilities, list):
        claimed = set(item for item in capabilities if isinstance(item, str))
        if claimed != expected["capabilities"] or len(capabilities) != len(expected["capabilities"]):
            findings.append("{}.capabilities: do not match the checked-in surface".format(label))


def _source_offset(source: str, position: Tuple[int, int]) -> int:
    """Convert a tokenize (line, column) position into a source offset."""
    line, column = position
    if line < 1:
        raise ValueError("invalid source position")
    offset = 0
    for _ in range(line - 1):
        newline = source.find("\n", offset)
        if newline < 0:
            raise ValueError("source position is outside the source text")
        offset = newline + 1
    return offset + column


def _source_tokens(source: str) -> List[tokenize.TokenInfo]:
    try:
        return list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError("cannot tokenize source: {}".format(exc))


def _literal_dictionary_fragment(
    source: str, name: str
) -> Tuple[str, Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """Extract one top-level direct dictionary assignment using tokens only.

    The engine is intentionally not parsed as a full module: it can contain
    syntax from Python versions newer than this utility's Python 3.9 floor.
    Tokenization locates the exact declared dictionary, then ``ast.parse`` is
    applied only to that self-contained expression.  Tokens are never used to
    infer registry keys.
    """
    tokens = _source_tokens(source)

    indent_depth = 0
    fragments: List[Tuple[str, Tuple[int, int], Tuple[int, int], Tuple[int, int]]] = []
    ignored = {tokenize.COMMENT, tokenize.NL}
    for index, token in enumerate(tokens):
        if token.type == tokenize.INDENT:
            indent_depth += 1
            continue
        if token.type == tokenize.DEDENT:
            indent_depth = max(0, indent_depth - 1)
            continue
        if (
            indent_depth != 0
            or token.type != tokenize.NAME
            or token.string != name
        ):
            continue

        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor].type in ignored:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].string not in {":", "="}:
            continue
        if tokens[cursor].string == ":":
            # An annotation may contain brackets, but the expected direct
            # declaration has one assignment operator before its newline.
            cursor += 1
            while cursor < len(tokens) and tokens[cursor].type != tokenize.NEWLINE:
                if tokens[cursor].string == "=":
                    break
                cursor += 1
            if cursor >= len(tokens) or tokens[cursor].string != "=":
                raise ValueError("{} must have a direct dictionary assignment".format(name))
        cursor += 1
        while cursor < len(tokens) and tokens[cursor].type in ignored:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].string != "{":
            raise ValueError("{} must have a direct dictionary assignment".format(name))

        start = tokens[cursor]
        braces = 0
        end_index: Optional[int] = None
        for candidate in range(cursor, len(tokens)):
            current = tokens[candidate]
            if current.type != tokenize.OP:
                continue
            if current.string == "{":
                braces += 1
            elif current.string == "}":
                braces -= 1
                if braces == 0:
                    end_index = candidate
                    break
        if end_index is None:
            raise ValueError("{} has an unclosed dictionary literal".format(name))
        tail = end_index + 1
        while tail < len(tokens) and tokens[tail].type in ignored:
            tail += 1
        if tail >= len(tokens) or tokens[tail].type != tokenize.NEWLINE:
            raise ValueError("{} must be assigned a direct dictionary literal".format(name))
        end = tokens[end_index]
        fragments.append((
            source[_source_offset(source, start.start):_source_offset(source, end.end)],
            token.start,
            start.start,
            end.end,
        ))

    if len(fragments) != 1:
        raise ValueError("expected exactly one top-level dictionary assignment to {}".format(name))
    return fragments[0]


def _next_significant(tokens: Sequence[tokenize.TokenInfo], index: int) -> Optional[int]:
    ignored = {tokenize.COMMENT, tokenize.NL}
    for cursor in range(index + 1, len(tokens)):
        if tokens[cursor].type not in ignored:
            return cursor
    return None


def _previous_significant(tokens: Sequence[tokenize.TokenInfo], index: int) -> Optional[int]:
    ignored = {tokenize.COMMENT, tokenize.NL}
    for cursor in range(index - 1, -1, -1):
        if tokens[cursor].type not in ignored:
            return cursor
    return None


def _literal_string(token: tokenize.TokenInfo) -> Optional[str]:
    if token.type != tokenize.STRING:
        return None
    source = token.string
    quote_start = 0
    while quote_start < len(source) and source[quote_start].lower() in {"r", "u", "b", "f"}:
        if source[quote_start].lower() == "f":
            return None
        quote_start += 1
    if quote_start >= len(source) or source[quote_start] not in {"'", '"'}:
        return None
    quote = source[quote_start]
    if not source.endswith(quote):
        return None
    # The validator only needs to distinguish a static string field from an
    # f-string/variable. Escape decoding is deliberately unnecessary here:
    # registry names are ASCII and appear verbatim in the policy checks.
    return source[quote_start + 1:-1]


def _top_level_function_body_spans(
    tokens: Sequence[tokenize.TokenInfo], name: str
) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Return lexical body spans for top-level functions named ``name``.

    The source-parity validator intentionally tokenizes the whole engine but
    AST-parses only its two registry literals so it remains usable on the
    project's Python 3.9 floor.  This small scope helper follows the same
    constraint: it recognizes a top-level ``def`` and its balanced INDENT /
    DEDENT body without executing or whole-module parsing the engine.
    """
    spans: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    indent_depth = 0
    for index, token in enumerate(tokens):
        if token.type == tokenize.INDENT:
            indent_depth += 1
            continue
        if token.type == tokenize.DEDENT:
            indent_depth = max(0, indent_depth - 1)
            continue
        if indent_depth != 0 or token.type != tokenize.NAME or token.string != "def":
            continue
        function_name = _next_significant(tokens, index)
        if (
            function_name is None
            or tokens[function_name].type != tokenize.NAME
            or tokens[function_name].string != name
        ):
            continue
        header_end = function_name + 1
        while header_end < len(tokens) and tokens[header_end].type != tokenize.NEWLINE:
            header_end += 1
        if header_end >= len(tokens):
            continue
        body_indent = header_end + 1
        while body_indent < len(tokens) and tokens[body_indent].type in {
            tokenize.COMMENT,
            tokenize.NL,
        }:
            body_indent += 1
        if body_indent >= len(tokens) or tokens[body_indent].type != tokenize.INDENT:
            continue
        body_depth = 1
        body_end = tokens[-1].end
        for cursor in range(body_indent + 1, len(tokens)):
            current = tokens[cursor]
            if current.type == tokenize.INDENT:
                body_depth += 1
            elif current.type == tokenize.DEDENT:
                body_depth -= 1
                if body_depth == 0:
                    body_end = current.start
                    break
        spans.append((tokens[body_indent].end, body_end))
    return spans


def _inside_unique_top_level_function(
    tokens: Sequence[tokenize.TokenInfo], position: Tuple[int, int], name: str
) -> bool:
    spans = _top_level_function_body_spans(tokens, name)
    return len(spans) == 1 and spans[0][0] <= position < spans[0][1]


def _approved_read_only_registry_call(
    tokens: Sequence[tokenize.TokenInfo], index: int, registry_name: str
) -> bool:
    """Recognize only the exact direct read calls the engine relies on.

    ``sorted(REGISTRY)`` is the validator's long-standing display/iteration
    allowance.  Renderer admission additionally compares the executing
    registry with immutable BASE through one exact
    ``set(RENDER_TARGETS)`` call in ``_gate_renderer_validate_pair``.
    Attribute calls, aliases, extra arguments, nested expressions, and the
    same call from any other function all remain fail-closed.
    """
    opening = _previous_significant(tokens, index)
    closing = _next_significant(tokens, index)
    if (
        opening is None
        or closing is None
        or tokens[opening].string != "("
        or tokens[closing].string != ")"
    ):
        return False
    caller = _previous_significant(tokens, opening)
    if caller is None or tokens[caller].type != tokenize.NAME:
        return False
    qualifier = _previous_significant(tokens, caller)
    if qualifier is not None and tokens[qualifier].string == ".":
        return False
    if tokens[caller].string == "sorted":
        return True
    return (
        tokens[caller].string == "set"
        and registry_name == "RENDER_TARGETS"
        and _inside_unique_top_level_function(
            tokens, tokens[index].start, "_gate_renderer_validate_pair"
        )
    )


def _approved_read_only_registry_literal(
    tokens: Sequence[tokenize.TokenInfo], index: int, registry_name: str
) -> bool:
    """Allow the renderer parser's exact ``node.id == REGISTRY_NAME`` tests.

    The literal is data used to inspect an immutable source blob; it is not a
    reflective lookup of the executing module.  Keeping this allowance tied
    to one unique helper and to an equality comparison on an ``.id`` field
    prevents a similarly named caller or dynamic access path from inheriting
    it.
    """
    if registry_name != "RENDER_TARGETS" or not _inside_unique_top_level_function(
        tokens, tokens[index].start, "_gate_renderer_registry_targets"
    ):
        return False
    equality = _previous_significant(tokens, index)
    attribute = _previous_significant(tokens, equality) if equality is not None else None
    dot = _previous_significant(tokens, attribute) if attribute is not None else None
    return (
        equality is not None
        and tokens[equality].string == "=="
        and attribute is not None
        and tokens[attribute].type == tokenize.NAME
        and tokens[attribute].string == "id"
        and dot is not None
        and tokens[dot].string == "."
    )


def _call_second_argument(
    tokens: Sequence[tokenize.TokenInfo], opening: int
) -> Optional[int]:
    """Return the first token of a direct call's second argument, if any."""
    depth = 0
    for cursor in range(opening, len(tokens)):
        token = tokens[cursor]
        if token.type != tokenize.OP:
            continue
        if token.string in {"(", "[", "{"}:
            depth += 1
        elif token.string in {")", "]", "}"}:
            depth -= 1
            if depth == 0:
                return None
        elif token.string == "," and depth == 1:
            return _next_significant(tokens, cursor)
    return None


def _dynamic_reflection_errors(source: str, registry_name: str) -> List[str]:
    """Fail loud on dynamic reflection that could bypass literal parity.

    ``getattr(args, "field")`` is a long-standing argparse convenience in
    the engine and is safe for this narrow scan. Every other reflective form
    is rejected when it names a registry, and unknown dynamic lookup is
    rejected rather than treated as evidence of registry immutability.
    """
    tokens = _source_tokens(source)
    findings: List[str] = []
    always_ambiguous = {
        "globals",
        "locals",
        "vars",
        "eval",
        "exec",
        "__builtins__",
        "builtins",
        "__import__",
        "__dict__",
        "__getattribute__",
    }
    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME:
            continue
        if token.string in always_ambiguous:
            findings.append("{}: source uses dynamic reflection {}()".format(registry_name, token.string))
            continue
        if token.string not in {"getattr", "setattr"}:
            continue
        opening = _next_significant(tokens, index)
        if opening is None or tokens[opening].string != "(":
            findings.append("{}: source uses ambiguous dynamic reflection {}".format(registry_name, token.string))
            continue
        first = _next_significant(tokens, opening)
        second = _call_second_argument(tokens, opening)
        second_literal = _literal_string(tokens[second]) if second is not None else None
        if second_literal in {"RENDER_TARGETS", "RUN_DRIVERS"}:
            findings.append(
                "{}: source reflection {}() names registry {!r}".format(
                    registry_name, token.string, second_literal
                )
            )
            continue
        if token.string == "getattr":
            if (
                first is not None
                and tokens[first].type == tokenize.NAME
                and tokens[first].string == "args"
                and second_literal is not None
            ):
                continue
            findings.append("{}: source getattr() has ambiguous dynamic provenance".format(registry_name))
        else:
            findings.append("{}: source setattr() has ambiguous dynamic provenance".format(registry_name))
    return findings


def _direct_registry_literal_errors(
    source: str,
    registry_name: str,
    declaration_start: Tuple[int, int],
    declaration_end: Tuple[int, int],
) -> List[str]:
    """Reject direct registry-name strings outside the canonical declaration.

    This is intentionally a syntactic tripwire, not a claim to prove all
    runtime data flow. A direct literal enables the common reflective paths
    (``locals()["RENDER_TARGETS"]`` and friends), so it must be surfaced.
    """
    findings: List[str] = []
    tokens = _source_tokens(source)
    for index, token in enumerate(tokens):
        if _literal_string(token) != registry_name:
            continue
        if declaration_start <= token.start and token.end <= declaration_end:
            continue
        if _approved_read_only_registry_literal(tokens, index, registry_name):
            continue
        findings.append(
            "{}: source contains direct registry literal outside canonical declaration".format(
                registry_name
            )
        )
    return findings


def _registry_mutation_errors(
    source: str, name: str, allowed_assignment: Tuple[int, int]
) -> List[str]:
    """Reject source-level rebinding and mutation without importing the engine."""
    tokens = _source_tokens(source)
    findings: List[str] = []
    assignment_ops = {"=", ":=", "+=", "-=", "*=", "/=", "//=", "%=", "**=", "&=", "|=", "^=", "<<=", ">>="}
    read_methods = {"items", "values", "keys", "get"}
    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME or token.string != name or token.start == allowed_assignment:
            continue
        previous = _previous_significant(tokens, index)
        following = _next_significant(tokens, index)
        if previous is not None and tokens[previous].type == tokenize.NAME and tokens[previous].string == "del":
            findings.append("{}: source deletes the registry".format(name))
            continue
        if following is None:
            continue
        next_token = tokens[following]
        if next_token.string in assignment_ops:
            findings.append("{}: source rebinds the registry".format(name))
            continue
        if next_token.string == ":":
            cursor = following + 1
            while cursor < len(tokens) and tokens[cursor].type != tokenize.NEWLINE:
                if tokens[cursor].string in assignment_ops:
                    findings.append("{}: source rebinds the registry".format(name))
                    break
                cursor += 1
            continue
        if next_token.string == ".":
            method_index = _next_significant(tokens, following)
            if method_index is None or tokens[method_index].type != tokenize.NAME:
                findings.append("{}: source uses an unapproved registry attribute".format(name))
            elif tokens[method_index].string not in read_methods:
                findings.append("{}: source uses unapproved registry method .{}".format(name, tokens[method_index].string))
            continue
        if next_token.string == "[":
            brackets = 0
            cursor = following
            while cursor < len(tokens):
                current = tokens[cursor]
                if current.type == tokenize.OP and current.string == "[":
                    brackets += 1
                elif current.type == tokenize.OP and current.string == "]":
                    brackets -= 1
                    if brackets == 0:
                        after = _next_significant(tokens, cursor)
                        if after is not None and tokens[after].string in assignment_ops:
                            findings.append("{}: source mutates a registry entry".format(name))
                        break
                cursor += 1
            continue
        if previous is not None and tokens[previous].type == tokenize.NAME and tokens[previous].string == "in":
            continue
        if _approved_read_only_registry_call(tokens, index, name):
            continue
        findings.append("{}: source uses the registry outside approved read-only forms".format(name))
    return findings


def _literal_dict_keys(source: str, name: str) -> Set[str]:
    """Read direct literal dictionary keys from source without executing it."""
    fragment, assignment, declaration_start, declaration_end = _literal_dictionary_fragment(source, name)
    mutation_errors = _registry_mutation_errors(source, name, assignment)
    mutation_errors.extend(_dynamic_reflection_errors(source, name))
    mutation_errors.extend(
        _direct_registry_literal_errors(source, name, declaration_start, declaration_end)
    )
    if mutation_errors:
        raise ValueError("; ".join(sorted(set(mutation_errors))))
    try:
        expression = ast.parse(fragment, mode="eval")
    except SyntaxError as exc:
        raise ValueError("{} dictionary is not valid Python AST: {}".format(name, exc))
    if not isinstance(expression.body, ast.Dict):
        raise ValueError("{} must be a dictionary literal".format(name))
    keys: Set[str] = set()
    for key in expression.body.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise ValueError("{} must use only string literal keys".format(name))
        if key.value in keys:
            raise ValueError("{} has duplicate key {!r}".format(name, key.value))
        keys.add(key.value)
    return keys


def _source_registry_keys(root_fd: int, findings: List[str]) -> Optional[Tuple[Set[str], Set[str]]]:
    descriptor = _open_relative(root_fd, ENGINE_PATH, str(ENGINE_PATH), findings, expect_directory=False)
    if descriptor is None:
        return None
    try:
        source_text = _read_descriptor(descriptor, str(ENGINE_PATH), findings)
        if source_text is None:
            return None
        return _literal_dict_keys(source_text, "RENDER_TARGETS"), _literal_dict_keys(source_text, "RUN_DRIVERS")
    except ValueError as exc:
        findings.append("{}: AST-only source parity failed: {}".format(ENGINE_PATH, exc))
        return None
    finally:
        os.close(descriptor)


def _validate_source_parity(root_fd: int, findings: List[str]) -> None:
    registries = _source_registry_keys(root_fd, findings)
    if registries is None:
        return
    targets, drivers = registries
    expected_targets = {
        claim["render_target"] for claim in EXPECTED_CLAIMS.values()
        if claim["render_target"] is not None
    }
    expected_drivers = {
        claim["driver"] for claim in EXPECTED_CLAIMS.values()
        if claim["driver"] is not None
    }
    for target in sorted(targets - expected_targets):
        findings.append("source parity: render target {!r} has no canonical manifest-backed claim".format(target))
    # FakeDriver is an existing test-only engine seam, not an adapter claim.
    for driver in sorted(drivers - expected_drivers - {"fake"}):
        findings.append("source parity: local process driver {!r} has no canonical manifest-backed claim".format(driver))
    for adapter_id in sorted(EXPECTED_CLAIMS):
        expected = EXPECTED_CLAIMS[adapter_id]
        target = expected["render_target"]
        driver = expected["driver"]
        if target is None and adapter_id in targets:
            findings.append("source parity: {!r} must not claim an absent render target".format(adapter_id))
        elif target is not None and target not in targets:
            findings.append("source parity: expected render target {!r} is absent".format(target))
        if driver is None and adapter_id in drivers:
            findings.append("source parity: {!r} must not claim an absent local process driver".format(adapter_id))
        elif driver is not None and driver not in drivers:
            findings.append("source parity: expected local process driver {!r} is absent".format(driver))


def _validate_manifest_directory(root_fd: int, findings: List[str]) -> Optional[Tuple[int, List[str]]]:
    directory_fd = _open_relative(root_fd, MANIFEST_DIRECTORY, str(MANIFEST_DIRECTORY), findings, expect_directory=True)
    if directory_fd is None:
        return None
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        findings.append("{}: cannot enumerate manifests: {}".format(MANIFEST_DIRECTORY, exc))
        os.close(directory_fd)
        return None
    found = set(names)
    expected = set(MANIFEST_NAMES)
    for name in sorted(expected - found):
        findings.append("{}: missing canonical manifest {!r}".format(MANIFEST_DIRECTORY, name))
    for name in sorted(found - expected):
        findings.append("{}: unexpected manifest input {!r}".format(MANIFEST_DIRECTORY, name))
    return directory_fd, sorted(expected & found)


def validate_repository(root: Path) -> List[str]:
    """Return deterministic advisory findings for one source checkout.

    The function is intentionally read-only and offline.  It performs no
    imports or execution of inspected source, and it never decides whether a
    change may merge, receive trust, or access a provider.
    """
    findings: List[str] = []
    root_fd = _open_root(root, findings)
    if root_fd is None:
        return sorted(set(findings))
    try:
        # Treat the checked-in schema as an input too, so symlink/special-file
        # substitutions cannot be hidden behind an otherwise-valid manifest tree.
        schema_fd = _open_relative(root_fd, SCHEMA_PATH, str(SCHEMA_PATH), findings, expect_directory=False)
        if schema_fd is not None:
            try:
                schema_data = _strict_json_descriptor(schema_fd, str(SCHEMA_PATH), findings)
                if not isinstance(schema_data, dict) or schema_data.get("$id") != "urn:twiss-io:tess-os:adapter-manifest:v1":
                    findings.append("{}: must be the advisory adapter-manifest v1 schema".format(SCHEMA_PATH))
            finally:
                os.close(schema_fd)

        manifest_directory = _validate_manifest_directory(root_fd, findings)
        if manifest_directory is not None:
            directory_fd, manifest_names = manifest_directory
            try:
                for manifest_name in manifest_names:
                    label = "adapters/manifests/{}".format(manifest_name)
                    manifest_fd = _open_relative(directory_fd, Path(manifest_name), label, findings, expect_directory=False)
                    if manifest_fd is None:
                        continue
                    try:
                        data = _strict_json_descriptor(manifest_fd, label, findings)
                    finally:
                        os.close(manifest_fd)
                    if data is not None:
                        _validate_manifest(root_fd, manifest_name, data, findings)
            finally:
                os.close(directory_fd)

        _validate_source_parity(root_fd, findings)
    finally:
        os.close(root_fd)
    return sorted(set(findings))
