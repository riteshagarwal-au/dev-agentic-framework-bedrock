output "cluster_arn" {
  description = "ARN of the ECS cluster the target app runs on."
  value       = aws_ecs_cluster.target.arn
}

output "cluster_name" {
  description = "Name of the ECS cluster the target app runs on."
  value       = aws_ecs_cluster.target.name
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository the target app's container images are pushed to."
  value       = aws_ecr_repository.target.arn
}

output "ecr_repository_url" {
  description = "URL of the ECR repository the target app's container images are pushed to."
  value       = aws_ecr_repository.target.repository_url
}

output "service_arn" {
  description = "ARN of the ECS service running the target app."
  value       = aws_ecs_service.target.id
}

output "task_definition_family_arn_pattern" {
  description = "ARN pattern (all revisions) of the target app's task definition family, suitable for scoping github-oidc's ecs_task_definition_arns."
  value       = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/${aws_ecs_task_definition.target.family}:*"
}

output "task_execution_role_arn" {
  description = "ARN of the ECS task execution role, for github-oidc's ecs_task_execution_role_arn (iam:PassRole grant)."
  value       = aws_iam_role.task_execution.arn
}
