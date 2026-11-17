from slotwright.layout import build_layout, layout_struct, linearize
from slotwright.parser import ParseError, parse_source

import pytest


def layout_of(body: str, contract: str = "C"):
    source = parse_source(f"contract {contract} {{ {body} }}")
    return build_layout(source, contract)


def slots(layout):
    return [(entry.name, entry.slot, entry.offset, entry.size) for entry in layout.entries]


def test_small_values_pack_into_one_slot():
    layout = layout_of(
        "address a; bool b; uint8 c; uint16 d;"
    )
    assert slots(layout) == [
        ("a", 0, 0, 20),
        ("b", 0, 20, 1),
        ("c", 0, 21, 1),
        ("d", 0, 22, 2),
    ]
    assert layout.total_slots == 1


def test_value_that_crosses_the_boundary_starts_a_new_slot():
    layout = layout_of("uint128 a; uint128 b; uint128 c; uint256 d;")
    assert slots(layout) == [
        ("a", 0, 0, 16),
        ("b", 0, 16, 16),
        ("c", 1, 0, 16),
        ("d", 2, 0, 32),
    ]
    assert layout.total_slots == 3


def test_mapping_arrays_and_strings_start_a_new_slot():
    layout = layout_of(
        "uint8 first; mapping(address => uint256) balances; string label; uint8 last;"
    )
    assert slots(layout) == [
        ("first", 0, 0, 1),
        ("balances", 1, 0, 32),
        ("label", 2, 0, 32),
        ("last", 3, 0, 1),
    ]
    assert layout.total_slots == 4


def test_inline_struct_occupies_its_own_block():
    layout = layout_of(
        "struct Pair { uint128 left; uint128 right; } uint256 before; Pair pair; uint256 after;"
    )
    assert slots(layout) == [
        ("before", 0, 0, 32),
        ("pair", 1, 0, 32),
        ("after", 2, 0, 32),
    ]
    assert layout.by_name()["pair"].kind == "struct"


def test_struct_fields_pack_like_top_level_values():
    source = parse_source(
        """
        contract C {
            struct Three { uint128 a; uint64 b; bool c; }
            Three public three;
        }
        """
    )
    struct_layout = layout_struct(source, "C", "Three")
    assert [(e.name, e.slot, e.offset, e.size) for e in struct_layout.entries] == [
        ("a", 0, 0, 16),
        ("b", 0, 16, 8),
        ("c", 0, 24, 1),
    ]
    layout = build_layout(source, "C")
    assert layout.total_slots == 1


def test_fixed_array_of_value_types_is_packed():
    layout = layout_of("uint256 first; uint32[4] words;")
    entry = layout.by_name()["words"]
    assert entry.slot == 1
    assert entry.offset == 0
    assert entry.size == 16
    assert entry.slots == 1


def test_fixed_array_of_addresses_spans_two_slots():
    layout = layout_of("address[2] owners;")
    entry = layout.by_name()["owners"]
    assert (entry.slot, entry.size, entry.slots) == (0, 40, 2)
    assert layout.total_slots == 2


def test_fixed_array_of_structs_multiplies_struct_slots():
    layout = layout_of(
        "struct Big { uint256 a; uint256 b; } Big[3] items;"
    )
    entry = layout.by_name()["items"]
    assert entry.slots == 6
    assert layout.total_slots == 6


def test_dynamic_array_of_structs_uses_one_slot():
    layout = layout_of("struct Big { uint256 a; uint256 b; } Big[] items;")
    assert layout.by_name()["items"].slots == 1
    assert layout.total_slots == 1


def test_inheritance_places_base_variables_first():
    source = parse_source(
        """
        contract Base { uint256 baseValue; bool baseFlag; }
        contract Child is Base { uint256 childValue; }
        """
    )
    layout = build_layout(source, "Child")
    assert [entry.name for entry in layout.entries] == [
        "baseValue",
        "baseFlag",
        "childValue",
    ]
    assert layout.by_name()["childValue"].slot == 2
    assert linearize(source, "Child") == ["Base", "Child"]


def test_diamond_inheritance_lists_a_shared_base_once():
    source = parse_source(
        """
        contract Root { uint256 root; }
        contract Left is Root { uint256 left; }
        contract Right is Root { uint256 right; }
        contract Leaf is Left, Right { uint256 leaf; }
        """
    )
    assert linearize(source, "Leaf") == ["Root", "Left", "Right", "Leaf"]


def test_constants_immutables_and_transient_variables_are_excluded():
    layout = layout_of(
        "uint256 public constant LIMIT = 5;"
        " address public immutable owner;"
        " bool private transient scratch;"
        " uint256 real;"
    )
    assert [entry.name for entry in layout.entries] == ["real"]
    assert layout.find("real").slot == 0
    assert [decl.name for decl in layout.skipped] == ["LIMIT", "owner", "scratch"]


def test_enum_takes_one_byte_and_packs():
    layout = layout_of("enum Kind { A, B } Kind kind; uint256 next;")
    assert slots(layout) == [("kind", 0, 0, 1), ("next", 1, 0, 32)]


def test_bytes_n_sizes():
    layout = layout_of("bytes1 a; bytes4 b; bytes32 c;")
    assert slots(layout) == [
        ("a", 0, 0, 1),
        ("b", 0, 1, 4),
        ("c", 1, 0, 32),
    ]


def test_address_payable_and_function_types():
    layout = layout_of("address payable receiver; function() external cb;")
    # 20 + 24 bytes cannot share one slot, so the function pointer starts slot 1.
    assert slots(layout) == [("receiver", 0, 0, 20), ("cb", 1, 0, 24)]


def test_unknown_contract_type_is_assumed_to_be_an_address():
    layout = layout_of("IERC20 token; uint8 flag;")
    assert slots(layout) == [("token", 0, 0, 20), ("flag", 0, 20, 1)]


def test_unknown_contract_name_raises():
    source = parse_source("contract C { uint256 a; }")
    with pytest.raises(ParseError):
        build_layout(source, "Missing")
