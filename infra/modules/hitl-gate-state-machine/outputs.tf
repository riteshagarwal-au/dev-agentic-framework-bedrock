output "state_machine_arn" {
  description = "ARN of the HITL gate wait/resume state machine. Passed by the HITL Broker's raiseGate (Task 9.1) as the target of StepFunctions.startExecution."
  value       = aws_sfn_state_machine.hitl_gate.arn
}

output "state_machine_name" {
  description = "Name of the HITL gate wait/resume state machine."
  value       = aws_sfn_state_machine.hitl_gate.name
}

output "state_machine_execution_role_arn" {
  description = "ARN of the IAM role assumed by the state machine itself (to invoke the notify target). NOT the policy to attach to the HITL Broker's role — see send_task_result_policy_arn for that."
  value       = aws_iam_role.state_machine_execution.arn
}

output "send_task_result_policy_arn" {
  description = <<-EOT
    ARN of a standalone `aws_iam_policy` granting only `states:SendTaskSuccess` and
    `states:SendTaskFailure`. Attach this to the HITL Broker's own IAM role (Task 9.2's `decide()`
    runtime identity) via `aws_iam_role_policy_attachment` in the composing root module/agent-IAM
    module (Task 3.4) — this module does not attach it to anything itself, since it does not own
    the broker's role.

    Note: these two actions do not support resource-level scoping to a specific state machine ARN
    (AWS requires Resource = "*" for them) — see send_task_result_policy_document for the exact
    policy JSON and the accompanying rationale.
  EOT
  value       = aws_iam_policy.hitl_broker_send_task.arn
}

output "send_task_result_policy_document" {
  description = "The IAM policy document (JSON) underlying send_task_result_policy_arn, for callers that prefer to inline/merge it rather than attach the standalone managed policy."
  value       = data.aws_iam_policy_document.hitl_broker_send_task.json
}

output "log_group_name" {
  description = "CloudWatch Logs group name for state machine execution history. Null when logging_enabled = false."
  value       = var.logging_enabled ? aws_cloudwatch_log_group.state_machine[0].name : null
}
