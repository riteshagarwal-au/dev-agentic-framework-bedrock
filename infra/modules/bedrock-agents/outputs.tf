output "agent_ids" {
  description = "Map of agent key -> Bedrock Agent ID, for the 5 core agents: discovery, devops, security, modernization, portfolio-assessment."
  value       = { for k, a in aws_bedrockagent_agent.this : k => a.agent_id }
}

output "agent_arns" {
  description = "Map of agent key -> Bedrock Agent ARN, for the same 5 agent keys as agent_ids."
  value       = { for k, a in aws_bedrockagent_agent.this : k => a.agent_arn }
}

output "discovery_agent_id" {
  description = "Convenience accessor for the Discovery agent's ID (equivalent to agent_ids[\"discovery\"])."
  value       = aws_bedrockagent_agent.this["discovery"].agent_id
}

output "discovery_agent_arn" {
  description = "Convenience accessor for the Discovery agent's ARN (equivalent to agent_arns[\"discovery\"])."
  value       = aws_bedrockagent_agent.this["discovery"].agent_arn
}

output "devops_agent_id" {
  description = "Convenience accessor for the DevOps agent's ID (equivalent to agent_ids[\"devops\"])."
  value       = aws_bedrockagent_agent.this["devops"].agent_id
}

output "devops_agent_arn" {
  description = "Convenience accessor for the DevOps agent's ARN (equivalent to agent_arns[\"devops\"])."
  value       = aws_bedrockagent_agent.this["devops"].agent_arn
}

output "security_agent_id" {
  description = "Convenience accessor for the Security agent's ID (equivalent to agent_ids[\"security\"])."
  value       = aws_bedrockagent_agent.this["security"].agent_id
}

output "security_agent_arn" {
  description = "Convenience accessor for the Security agent's ARN (equivalent to agent_arns[\"security\"])."
  value       = aws_bedrockagent_agent.this["security"].agent_arn
}

output "modernization_agent_id" {
  description = "Convenience accessor for the Modernization agent's ID (equivalent to agent_ids[\"modernization\"])."
  value       = aws_bedrockagent_agent.this["modernization"].agent_id
}

output "modernization_agent_arn" {
  description = "Convenience accessor for the Modernization agent's ARN (equivalent to agent_arns[\"modernization\"])."
  value       = aws_bedrockagent_agent.this["modernization"].agent_arn
}

output "portfolio_assessment_agent_id" {
  description = "Convenience accessor for the Portfolio Assessment agent's ID (equivalent to agent_ids[\"portfolio-assessment\"])."
  value       = aws_bedrockagent_agent.this["portfolio-assessment"].agent_id
}

output "portfolio_assessment_agent_arn" {
  description = "Convenience accessor for the Portfolio Assessment agent's ARN (equivalent to agent_arns[\"portfolio-assessment\"])."
  value       = aws_bedrockagent_agent.this["portfolio-assessment"].agent_arn
}

output "action_group_ids" {
  description = "Map of agent key -> placeholder action group ID (see README.md limitation: all action groups are created DISABLED pending Lambda executor wiring)."
  value       = { for k, g in aws_bedrockagent_agent_action_group.this : k => g.action_group_id }
}
