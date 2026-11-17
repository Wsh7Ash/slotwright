// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Upgrade that adds a new variable by consuming part of the storage gap.
contract Vault {
    address public owner;
    bool public paused;
    uint96 public feeBps;
    uint256 public totalDeposits;
    mapping(address => uint256) public balances;
    uint256 public lastSynced;      // consumes slot 5, taken from the gap below
    uint256[7] private __gap;
}
