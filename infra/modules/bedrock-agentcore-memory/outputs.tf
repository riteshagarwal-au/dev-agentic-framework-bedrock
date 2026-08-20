output "memory_id" {
  description = "ID of the AgentCore Memory resource, for agents/hook pipeline to reference (e.g. Task 10.3's Memory.summarizeAndEvict call)."
  value       = awscc_bedrockagentcore_memory.this.memory_id
}

output "memory_arn" {
  description = "ARN of the AgentCore Memory resource."
  value       = awscc_bedrockagentcore_memory.this.memory_arn
}

output "memory_name" {
  description = "Name of the AgentCore Memory resource."
  value       = local.memory_name
}

output "memory_status" {
  description = "Status of the Memory resource (CREATING, ACTIVE, DELETING, FAILED)."
  value       = awscc_bedrockagentcore_memory.this.status
}

output "memory_execution_role_arn" {
  description = "ARN of the memory execution role, if created by this module (var.create_memory_execution_role = true), or the passed-in var.memory_execution_role_arn, or null if neither is set."
  value       = local.memory_execution_role_arn
}

output "agent_memory_access_policy_arn" {
  description = <<-EOT
    ARN of the standalone IAM policy granting read/write access to this memory's bedrock-agentcore
    data-plane actions, or null if var.create_agent_access_policy = false. Attach this to each
    agent's least-privilege IAM role (Task 3.4) that needs to call Memory.summarizeAndEvict or
    retrieve prior long-term memory records.
  EOT
  value       = var.create_agent_access_policy ? aws_iam_policy.agent_memory_access[0].arn : null
}

output "strategy_types_configured" {
  description = "The list of memory strategy types configured on this Memory resource (e.g. [\"SUMMARIZATION\"]), for quick visibility into what long-term extraction is active."
  value       = [for s in var.memory_strategies : s.type]
}
