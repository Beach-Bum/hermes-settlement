// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentRegistry — minimal ERC-8004 identity and reputation registry
/// @notice Reference implementation for the nous-agent demo.
/// @dev Proof-of-shape, not production. ERC-8004 is early — this captures
///      the interface shape (register, reputation, validation) without
///      claiming to be a canonical implementation.
contract AgentRegistry {

    struct Agent {
        bytes32 pubKeyHash;
        bytes32 capabilityHash;
        uint256 stake;
        uint256 registeredAt;
        uint256 totalTasks;
        uint256 successfulTasks;
        bool active;
    }

    mapping(address => Agent) public agents;
    address[] public agentList;

    event AgentRegistered(address indexed agent, bytes32 pubKeyHash, uint256 stake);
    event ReputationUpdated(address indexed agent, uint256 totalTasks, uint256 successfulTasks);
    event TaskCompleted(address indexed agent, bool success);

    function register(bytes32 pubKeyHash, bytes32 capabilityHash) external payable {
        require(!agents[msg.sender].active, "Already registered");
        require(msg.value > 0, "Stake required");

        agents[msg.sender] = Agent({
            pubKeyHash: pubKeyHash,
            capabilityHash: capabilityHash,
            stake: msg.value,
            registeredAt: block.number,
            totalTasks: 0,
            successfulTasks: 0,
            active: true
        });
        agentList.push(msg.sender);

        emit AgentRegistered(msg.sender, pubKeyHash, msg.value);
    }

    function recordTask(bool success) external {
        require(agents[msg.sender].active, "Not registered");
        agents[msg.sender].totalTasks++;
        if (success) {
            agents[msg.sender].successfulTasks++;
        }
        emit TaskCompleted(msg.sender, success);
        emit ReputationUpdated(
            msg.sender,
            agents[msg.sender].totalTasks,
            agents[msg.sender].successfulTasks
        );
    }

    function getReputation(address agent) external view returns (uint256 score, uint256 total, uint256 successful) {
        Agent storage a = agents[agent];
        if (a.totalTasks == 0) return (0, 0, 0);
        // Score as basis points (0-10000) for precision without floats
        score = (a.successfulTasks * 10000) / a.totalTasks;
        total = a.totalTasks;
        successful = a.successfulTasks;
    }

    function isRegistered(address agent) external view returns (bool) {
        return agents[agent].active;
    }

    function agentCount() external view returns (uint256) {
        return agentList.length;
    }
}
