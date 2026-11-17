// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Example used by the slotwright quick start.
contract Vault {
    address public owner;
    bool public paused;
    uint96 public feeBps;
    uint256 public totalDeposits;
    mapping(address => uint256) public balances;
    uint256[8] private __gap;
}
