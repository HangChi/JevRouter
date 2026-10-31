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
    assert len(cases) == 53
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


def test_a_write_case_states_what_to_write() -> None:
    """不含内容的 goal 用 `ask_user` 回答才是正确的。

    第一次真实评测里所有写入用例都失分了，因为 goal 只说“保存会议纪要”却没
    给纪要：两个路由层都转而询问用户，而这恰恰是对的。因此一个期望
    `write_file` 的用例必须带上目标路径和内容，否则它什么都没检验。
    """
    for case in committed():
        if case.expected_action != "write_file":
            continue
        assert "." in case.goal, f"{case.id} names no destination file"


def test_an_email_case_states_a_recipient() -> None:
    """邮件同理：没有地址时，询问用户就是正确的下一步。"""
    for case in committed():
        if case.expected_action != "send_mock_email":
            continue
        assert "@" in case.goal, f"{case.id} names no recipient"


def test_the_set_measures_restraint_as_well_as_action() -> None:
    """信息确实缺失的用例必须期望 `ask_user`。

    没有这些用例，`ask_user` 比例上升就无法与一个正确地拒绝猜测的路由层区分开。
    """
    asking = [case for case in committed() if case.expected_action == "ask_user"]
    assert len(asking) >= 5, "the case set needs cases where asking is correct"


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
    with pytest.raises(CaseFileError, match="版本"):
        load_cases(path)


def test_missing_version_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, {"cases": [case_entry()]})
    with pytest.raises(CaseFileError, match="版本"):
        load_cases(path)


def test_empty_case_list_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, {"version": CASE_FILE_VERSION, "cases": []})
    with pytest.raises(CaseFileError, match="至少"):
        load_cases(path)


def test_duplicate_id_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {"version": CASE_FILE_VERSION, "cases": [case_entry(), case_entry()]},
    )
    with pytest.raises(CaseFileError, match="重复"):
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
    with pytest.raises(CaseFileError, match="无效"):
        load_cases(path)


def test_untrimmed_action_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {
            "version": CASE_FILE_VERSION,
            "cases": [case_entry(expected_action=" calculator ", allowed_actions=[" calculator "])],
        },
    )
    with pytest.raises(CaseFileError, match="无效"):
        load_cases(path)


def test_repeated_allowed_action_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {
            "version": CASE_FILE_VERSION,
            "cases": [case_entry(allowed_actions=["calculator", "calculator"])],
        },
    )
    with pytest.raises(CaseFileError, match="无效"):
        load_cases(path)


def test_unknown_field_is_refused(tmp_path: Any) -> None:
    path = write_file(
        tmp_path,
        {"version": CASE_FILE_VERSION, "cases": [case_entry(unexpected="x")]},
    )
    with pytest.raises(CaseFileError, match="无效"):
        load_cases(path)


def test_missing_file_is_refused() -> None:
    with pytest.raises(CaseFileError, match="不存在"):
        load_cases("/nonexistent/cases.json")


def test_malformed_json_is_refused(tmp_path: Any) -> None:
    path = tmp_path / "cases.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CaseFileError, match="不是合法的 JSON"):
        load_cases(path)


def test_non_object_file_is_refused(tmp_path: Any) -> None:
    path = write_file(tmp_path, [case_entry()])
    with pytest.raises(CaseFileError, match="JSON 对象"):
        load_cases(path)
