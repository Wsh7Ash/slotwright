// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Upgrade that inserts state in the middle: every later variable is relocated.
contract Vault {
    address public owner;
    bool public paused;
    uint128 public pendingFees;
    uint96 public feeBps;
    uint256 public totalDeposits;
    mapping(address => uint256) public balances;
    uint256[8] private __gap;
}
