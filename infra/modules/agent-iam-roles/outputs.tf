output "role_arns" {
  description = <<-EOT
    Map of agent key -> IAM role ARN, for the 7 agent keys: supervisor, discovery, devops,
    security, modernization, portfolio-assessment, pr-reviewer. Task 13.7's Bedrock Agent
    resources consume this map to attach each agent to its own distinct execution role.
  EOT
  value       = { for k, r in aws_iam_role.agent : k => r.arn }
}

output "role_names" {
  description = "Map of agent key -> IAM role name, for the same 7 agent keys as role_arns."
  value       = { for k, r in aws_iam_role.agent : k => r.name }
}

output "supervisor_role_arn" {
  description = "Convenience accessor for the Supervisor role's ARN (equivalent to role_arns[\"supervisor\"])."
  value       = aws_iam_role.agent["supervisor"].arn
}

output "discovery_role_arn" {
  description = "Convenience accessor for the Discovery agent role's ARN (equivalent to role_arns[\"discovery\"])."
  value       = aws_iam_role.agent["discovery"].arn
}

output "devops_role_arn" {
  description = "Convenience accessor for the DevOps agent role's ARN (equivalent to role_arns[\"devops\"])."
  value       = aws_iam_role.agent["devops"].arn
}

output "security_role_arn" {
  description = "Convenience accessor for the Security agent role's ARN (equivalent to role_arns[\"security\"])."
  value       = aws_iam_role.agent["security"].arn
}

output "modernization_role_arn" {
  description = "Convenience accessor for the Modernization agent role's ARN (equivalent to role_arns[\"modernization\"])."
  value       = aws_iam_role.agent["modernization"].arn
}

output "portfolio_assessment_role_arn" {
  description = "Convenience accessor for the Portfolio Assessment agent role's ARN (equivalent to role_arns[\"portfolio-assessment\"])."
  value       = aws_iam_role.agent["portfolio-assessment"].arn
}

output "pr_reviewer_role_arn" {
  description = "Convenience accessor for the PR-Reviewer agent role's ARN (equivalent to role_arns[\"pr-reviewer\"])."
  value       = aws_iam_role.agent["pr-reviewer"].arn
}
