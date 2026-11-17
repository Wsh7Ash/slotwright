import pytest

from slotwright.parser import ParseError, parse_source


def test_contracts_and_bases_are_read():
    source = parse_source(
        """
        pragma solidity ^0.8.24;
        contract Base { uint256 baseValue; }
        abstract contract Middle is Base { bool flag; }
        contract Child is Middle, Other { address owner; }
        """
    )
    assert source.order == ["Base", "Middle", "Child"]
    assert source.contracts["Middle"].bases == ("Base",)
    assert source.contracts["Child"].bases == ("Middle", "Other")
    assert source.contracts["Child"].kind == "contract"


def test_contract_kinds():
    source = parse_source(
        """
        interface IThing { function ping() external; }
        library Math { function add(uint256 a) internal pure returns (uint256) { return a; } }
        contract Thing { uint256 value; }
        """
    )
    assert source.contracts["IThing"].kind == "interface"
    assert source.contracts["Math"].kind == "library"
    assert source.contracts["Thing"].kind == "contract"


def test_comments_strings_and_function_bodies_do_not_leak_declarations():
    source = parse_source(
        """
        contract Tricky {
            // uint256 commentedOut;
            /* bool alsoCommented; */
            string public label = "a string with ; and } inside";
            uint256 public real;

            function mutate() public {
                uint256 localVar = 3;
                label = "{still a string}";
            }

            modifier guarded() { _; }
        }
        """
    )
    names = [decl.name for decl in source.contracts["Tricky"].vars]
    assert names == ["label", "real"]


def test_attributes_constants_and_immutables_are_flagged():
    source = parse_source(
        """
        contract Flags {
            uint256 public constant LIMIT = 100;
            address public immutable owner;
            bool private transient scratch;
            uint256 public normal;
        }
        """
    )
    decls = {decl.name: decl for decl in source.contracts["Flags"].vars}
    assert decls["LIMIT"].is_constant
    assert decls["owner"].is_immutable
    assert decls["scratch"].is_transient
    assert decls["normal"].occupies_storage
    assert not decls["LIMIT"].occupies_storage


def test_override_and_visibility_are_stripped_from_the_type():
    source = parse_source(
        """
        contract Parent { function hook() public virtual {} }
        contract Child is Parent {
            mapping(address => uint256) internal balances;
            uint256[] private list;
        }
        """
    )
    decls = {decl.name: decl for decl in source.contracts["Child"].vars}
    assert decls["balances"].type_str == "mapping(address => uint256)"
    assert decls["list"].type_str == "uint256[]"


def test_struct_and_enum_are_collected():
    source = parse_source(
        """
        contract Shapes {
            enum Kind { A, B, C }
            struct Pair { uint128 left; uint128 right; }
            Pair public pair;
        }
        """
    )
    contract = source.contracts["Shapes"]
    assert [struct.name for struct in contract.structs] == ["Pair"]
    assert [field.name for field in contract.structs[0].fields] == ["left", "right"]
    assert contract.enums == ("Kind",)


def test_line_numbers_point_at_the_declaration():
    source = parse_source(
        "\n\ncontract Lines {\n    uint256 a;\n    uint256 b;\n}\n"
    )
    decls = {decl.name: decl for decl in source.contracts["Lines"].vars}
    assert decls["a"].line == 4
    assert decls["b"].line == 5


def test_no_contract_is_an_error():
    with pytest.raises(ParseError):
        parse_source("pragma solidity ^0.8.24;")


def test_unbalanced_braces_report_a_parse_error():
    with pytest.raises(ParseError):
        parse_source("contract Broken { uint256 a;")


def test_default_contract_is_the_last_declared():
    source = parse_source(
        "contract First { uint256 a; } contract Second { bool b; }"
    )
    assert source.require(None).name == "Second"
    assert source.require("First").name == "First"
