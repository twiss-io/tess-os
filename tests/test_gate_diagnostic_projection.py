"""Regression coverage for redacted gate decision projections.

The gate keeps raw failure detail inside the decision engine.  These tests
exercise only the public-code classifier: static internal grouping labels may
be unwrapped, but unknown detail must never escape the allowlist.
"""


def test_renderer_wrapper_preserves_known_admission_source_code(engine):
    raw = "[renderer-base] ADMISSION_EVENT_SOURCE_REQUIRED: private event context"

    assert engine._decision_reason_code(raw) == "ADMISSION_EVENT_SOURCE_REQUIRED"
    assert engine._safe_decision_reason(raw) == (
        "ADMISSION_EVENT_SOURCE_REQUIRED: "
        "an authoritative admission event source is required"
    )


def test_each_known_static_wrapper_is_unwrapped_before_code_mapping(engine):
    assert engine._decision_reason_code(
        "[contract] BASE_REQUIRED: private immutable ref"
    ) == "BASE_REQUIRED"
    assert engine._decision_reason_code(
        "[gate] ADMISSION_EVENT_SOURCE_REQUIRED: private event context"
    ) == "ADMISSION_EVENT_SOURCE_REQUIRED"


def test_unknown_wrapped_reason_stays_redacted(engine):
    sentinels = [
        f"{wrapper}PRIVATE_SENTINEL: do not disclose this value"
        for wrapper in engine._DECISION_REASON_WRAPPERS
    ] + [
        "[renderer-base] [gate] ADMISSION_EVENT_SOURCE_REQUIRED: private nested value",
    ]

    assert all(
        engine._decision_reason_code(sentinel) == "INTERNAL_ERROR_REDACTED"
        for sentinel in sentinels
    )
    safe = engine._safe_gate_result(
        {"blocked": True, "reasons": sentinels, "changed_paths": ["secret/path"]},
        phase="ci",
    )
    assert safe == {
        "phase": "ci",
        "blocked": True,
        "reasons": [
            "INTERNAL_ERROR_REDACTED: an internal failure was redacted",
            "INTERNAL_ERROR_REDACTED: an internal failure was redacted",
            "INTERNAL_ERROR_REDACTED: an internal failure was redacted",
            "INTERNAL_ERROR_REDACTED: an internal failure was redacted",
        ],
        "changed_paths_count": 1,
    }
    assert "PRIVATE_SENTINEL" not in repr(safe)


def test_topology_codes_project_only_exact_engine_owned_prefixes(engine):
    exact_policy_reason = (
        "[policy] C1_PUBLIC_KEY_PATH_CONTAINMENT: private candidate key path"
    )
    assert engine._decision_reason_code(exact_policy_reason) == (
        "C1_PUBLIC_KEY_PATH_CONTAINMENT"
    )
    assert engine._safe_decision_reason(exact_policy_reason) == (
        "C1_PUBLIC_KEY_PATH_CONTAINMENT: "
        "a registered public-key path failed containment validation"
    )
    assert engine._decision_reason_code(
        "CI_PR_EVENT_REQUIRED: private event payload"
    ) == "CI_PR_EVENT_REQUIRED"

    unsafe_variants = [
        "C1_PUBLIC_KEY_PATH_CONTAINMENT_EVIL: private candidate key path",
        "prefix C1_PUBLIC_KEY_PATH_CONTAINMENT: private candidate key path",
        "[policy] C1_PUBLIC_KEY_PATH_CONTAINMENT_EVIL: private candidate key path",
        "[policy] C1_PUBLIC_KEY_PATH_CONTAINMENT ../../private/key.asc",
        "[policy] [gate] C1_PUBLIC_KEY_PATH_CONTAINMENT: private candidate key path",
        "CI_PR_EVENT_REQUIRED_EVIL: private event payload",
        "[renderer-base] [gate] CI_PR_EVENT_REQUIRED: private event payload",
        "[policy] CI_PR_EVENT_REQUIRED: private event payload",
    ]
    assert all(
        engine._decision_reason_code(variant) == "INTERNAL_ERROR_REDACTED"
        for variant in unsafe_variants
    )
    projected = engine._safe_gate_result(
        {"blocked": True, "reasons": unsafe_variants, "changed_paths": ["private/path"]},
        phase="ci",
    )
    assert all(
        reason == "INTERNAL_ERROR_REDACTED: an internal failure was redacted"
        for reason in projected["reasons"]
    )
    assert "private" not in repr(projected)
