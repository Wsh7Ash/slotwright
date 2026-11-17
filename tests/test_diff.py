from slotwright.diff import diff_layouts
from slotwright.layout import build_layout
from slotwright.parser import parse_source


def compare(old_body: str, new_body: str):
    old_source = parse_source(f"contract C {{ {old_body} }}")
    new_source = parse_source(f"contract C {{ {new_body} }}")
    return diff_layouts(
        build_layout(old_source, "C"), build_layout(new_source, "C")
    )


def kinds(result):
    return [(change.kind, change.severity, change.name) for change in result.changes]


def test_identical_layouts_have_no_changes():
    result = compare("uint256 a; bool b;", "uint256 a; bool b;")
    assert result.changes == ()
    assert result.verdict == "SAFE"


def test_appending_after_the_last_slot_is_safe():
    result = compare("uint256 a; bool b;", "uint256 a; bool b; uint256 c;")
    assert kinds(result) == [("appended", "safe", "c")]
    assert result.verdict == "SAFE"
    assert (result.old_slots, result.new_slots) == (2, 3)


def test_appending_that_reuses_free_space_in_the_last_slot_is_safe():
    result = compare("uint128 a;", "uint128 a; uint128 b;")
    assert kinds(result) == [("appended", "safe", "b")]
    assert result.verdict == "SAFE"


def test_inserting_in_the_middle_is_breaking_for_every_later_variable():
    result = compare(
        "uint256 a; uint256 b;", "uint256 a; uint256 x; uint256 b;"
    )
    assert ("inserted", "breaking", "x") in kinds(result)
    assert ("moved", "breaking", "b") in kinds(result)
    assert result.verdict == "BREAKING"


def test_changing_the_type_is_breaking():
    result = compare("uint128 amount;", "uint256 amount;")
    assert kinds(result) == [("type-changed", "breaking", "amount")]
    assert result.verdict == "BREAKING"


def test_removing_the_last_variable_is_safe():
    result = compare("uint256 a; uint256 b;", "uint256 a;")
    assert kinds(result) == [("removed-tail", "safe", "b")]
    assert result.verdict == "SAFE"


def test_removing_a_middle_variable_is_breaking():
    result = compare("uint256 a; uint256 b; uint256 c;", "uint256 a; uint256 c;")
    assert ("removed", "breaking", "b") in kinds(result)
    assert ("moved", "breaking", "c") in kinds(result)
    assert result.verdict == "BREAKING"


def test_reordering_is_breaking():
    result = compare("uint128 a; uint128 b;", "uint128 b; uint128 a;")
    assert {change.kind for change in result.changes} == {"moved"}
    assert result.verdict == "BREAKING"


def test_shrinking_the_storage_gap_is_breaking():
    result = compare(
        "uint256 value; uint256[8] private __gap;",
        "uint256 value; uint256[7] private __gap;",
    )
    assert ("gap-shrunk", "breaking", "__gap") in kinds(result)
    assert result.verdict == "BREAKING"


def test_consuming_the_storage_gap_is_safe_when_it_shrinks_by_the_same_amount():
    result = compare(
        "uint256 value; uint256[8] private __gap;",
        "uint256 value; uint256 added; uint256[7] private __gap;",
    )
    assert kinds(result) == [("gap-consumed", "safe", "added")]
    assert result.verdict == "SAFE"
    assert (result.old_slots, result.new_slots) == (9, 9)


def test_consuming_the_gap_without_shrinking_it_is_breaking():
    result = compare(
        "uint256[8] private __gap;",
        "uint256 added; uint256[8] private __gap;",
    )
    assert result.verdict == "BREAKING"


def test_growing_the_storage_gap_is_only_a_warning():
    result = compare("uint256[8] private __gap;", "uint256[9] private __gap;")
    assert kinds(result) == [("gap-grown", "warning", "__gap")]
    assert result.verdict == "SAFE"


def test_inherited_variables_are_included_in_the_diff():
    old = parse_source(
        "contract Base { uint256 baseValue; } contract Child is Base { uint256 childValue; }"
    )
    new = parse_source(
        "contract Base { uint256 baseValue; } contract Child is Base { uint256 inserted; uint256 childValue; }"
    )
    result = diff_layouts(build_layout(old, "Child"), build_layout(new, "Child"))
    assert ("inserted", "breaking", "inserted") in kinds(result)
    assert ("moved", "breaking", "childValue") in kinds(result)
