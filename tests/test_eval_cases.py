from __future__ import annotations

import json
from typing import Any

import pytest

from evals.cases import CASE_FILE_VERSION, CaseFileError, EvalCase, load_cases

CONFIRMING_ACTIONS = frozenset({"write_file", "send_mock_email"})


def committed() -> tuple[EvalCase, ...]:
    return load_cases()


def test_committed_file_is_valid_and_covers_every_action() -> None:
    cases = committed()
    assert len(cases) == 50
    assert {case.expected_action for case in cases} == {
        "calculator",
        "knowledge_search",
        "web_search",
        "write_file",
        "send_mock_email",
        "ask_user",
        "delegate_to_llm",
        "finish",
    }


def test_committed_ids_are_unique() -> None:
    ids = [case.id for case in committed()]
    assert len(set(ids)) == len(ids)


def test_committed_confirmation_flags_follow_the_risk_classes() -> None:
    for case in committed():
        assert case.requires_confirmation is (case.expected_action in CONFIRMING_ACTIONS), case.id


def test_committed_file_has_multi_action_allowed_sets() -> None:
    ambiguous = [case.id for case in committed() if len(case.allowed_actions) > 1]
    assert ambiguous, "allowed-match should differ from expected-match on some cases"


def write_file(tmp_path: Any, payload: Any) -> Any:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def case_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": "case-1",
        "goal": "do the thing",
        "expected_action": "calculator",
        "allowed_actions": ["calculator"],
        "requires_confirmation": False,
    }
    entry.update(overrides)
    return entry


def test_unknown_version_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, {"version": CASE_FILE_VERSION + 1, "cases": [case_entry()]})
    with pytest.raises(CaseFileError, match="version"):
        load_cases(path)


def test_missing_version_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, {"cases": [case_entry()]})
    with pytest.raises(CaseFileError, match="version"):
        load_cases(path)


def test_empty_case_list_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, {"version": CASE_FILE_VERSION, "cases": []})
    with pytest.raises(CaseFileError, match="at least one"):
        load_cases(path)


def test_duplicate_id_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {"version": CASE_FILE_VERSION, "cases": [case_entry(), case_entry()]},
    )
    with pytest.raises(CaseFileError, match="duplicate"):
        load_cases(path)


def test_expected_outside_allowed_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {"version": CASE_FILE_VERSION, "cases": [case_entry(expected_action="web_search")]},
    )
    with pytest.raises(CaseFileError, match="expected_action"):
        load_cases(path)


def test_blank_action_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {
            "version": CASE_FILE_VERSION,
            "cases": [case_entry(expected_action="  ", allowed_actions=["  "])],
        },
    )
    with pytest.raises(CaseFileError, match="invalid"):
        load_cases(path)


def test_untrimmed_action_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {
            "version": CASE_FILE_VERSION,
            "cases": [case_entry(expected_action=" calculator ", allowed_actions=[" calculator "])],
        },
    )
    with pytest.raises(CaseFileError, match="invalid"):
        load_cases(path)


def test_repeated_allowed_action_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {
            "version": CASE_FILE_VERSION,
            "cases": [case_entry(allowed_actions=["calculator", "calculator"])],
        },
    )
    with pytest.raises(CaseFileError, match="invalid"):
        load_cases(path)


def test_unknown_field_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {"version": CASE_FILE_VERSION, "cases": [case_entry(unexpected="x")]},
    )
    with pytest.raises(CaseFileError, match="invalid"):
        load_cases(path)


def test_missing_file_is_refused() -> None:
    with pytest.raises(CaseFileError, match="does not exist"):
        load_cases("/nonexistent/cases.json")


def test_malformed_json_is_refused(tmp_path: Any) -> None:
    path = tmp_path / "cases.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CaseFileError, match="not valid JSON"):
        load_cases(path)


def test_non_object_file_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, [case_entry()])
    with pytest.raises(CaseFileError, match="JSON object"):
        load_cases(path)
