import json

from slotwright.cli import main

V1 = """
contract Vault {
    address public owner;
    uint128 public total;
    uint128 public shares;
}
"""

V2_BREAKING = """
contract Vault {
    address public owner;
    uint64 public fee;
    uint64 public feeDenominator;
    uint128 public total;
    uint128 public shares;
}
"""

V2_SAFE = V1.replace("}", "    uint256 public extra;\n}")


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_layout_text_output(tmp_path, capsys):
    path = write(tmp_path, "v.sol", V1)
    assert main(["layout", path]) == 0
    out = capsys.readouterr().out
    assert "Storage layout: Vault" in out
    assert "owner" in out
    assert "total" in out


def test_layout_json_output(tmp_path, capsys):
    path = write(tmp_path, "v.sol", V1)
    assert main(["layout", path, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract"] == "Vault"
    assert payload["total_slots"] == 2
    assert payload["entries"][0]["name"] == "owner"
    assert payload["entries"][0]["offset"] == 0


def test_struct_layout_output(tmp_path, capsys):
    path = write(
        tmp_path,
        "s.sol",
        "contract C { struct Pair { uint128 a; uint128 b; } Pair p; }",
    )
    assert main(["layout", path, "--struct", "Pair", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["name"] for entry in payload["entries"]] == ["a", "b"]


def test_diff_reports_breaking_without_failing_by_default(tmp_path, capsys):
    old = write(tmp_path, "old.sol", V1)
    new = write(tmp_path, "new.sol", V2_BREAKING)
    assert main(["diff", old, new]) == 0
    out = capsys.readouterr().out
    assert "Verdict: BREAKING" in out
    assert "inserted" in out


def test_fail_on_breaking_sets_exit_code(tmp_path):
    old = write(tmp_path, "old.sol", V1)
    new = write(tmp_path, "new.sol", V2_BREAKING)
    assert main(["diff", old, new, "--fail-on-breaking"]) == 1


def test_safe_upgrade_exits_zero_with_gate(tmp_path, capsys):
    old = write(tmp_path, "old.sol", V1)
    new = write(tmp_path, "new.sol", V2_SAFE)
    assert main(["diff", old, new, "--fail-on-breaking", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "SAFE"


def test_contracts_command(tmp_path, capsys):
    path = write(
        tmp_path,
        "multi.sol",
        "interface I { function f() external; } contract A { uint256 x; } contract B is A {}",
    )
    assert main(["contracts", path]) == 0
    out = capsys.readouterr().out
    assert "I (interface)" in out
    assert "B (contract) is A" in out


def test_unknown_contract_is_an_error(tmp_path, capsys):
    path = write(tmp_path, "v.sol", V1)
    assert main(["layout", path, "--contract", "Nope"]) == 2
    assert "not found" in capsys.readouterr().err


def test_missing_file_is_an_error(capsys):
    assert main(["layout", "does-not-exist.sol"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_demo_reports_a_breaking_insert(capsys):
    assert main(["demo"]) == 1
    out = capsys.readouterr().out
    assert "slot" in out
    assert "Verdict: BREAKING" in out


def test_demo_json_shape(capsys):
    assert main(["demo", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["diff"]["verdict"] == "BREAKING"
    assert payload["new"]["total_slots"] > payload["old"]["total_slots"]


def test_explain_topics(capsys):
    for topic in ("packing", "upgrades", "gaps"):
        assert main(["explain", topic]) == 0
        assert capsys.readouterr().out.strip()
