variable "state_machine_name" {
  description = "Name of the Step Functions state machine that brokers the HITL gate wait/resume (Component 4)."
  type        = string
  default     = "daf-hitl-gate"

  validation {
    condition     = length(var.state_machine_name) > 0
    error_message = "state_machine_name must not be empty."
  }
}

variable "notify_target_lambda_arn" {
  description = <<-EOT
    ARN of a Lambda function invoked (via the `.waitForTaskToken` integration pattern) when a gate
    is raised. This module does NOT create or implement that Lambda — it only wires the state
    machine to call it. The Lambda receives the held task token (`$$.Task.Token`) plus the
    gate/run/ticket identifiers in its payload and is responsible for making that token available
    to the HITL Broker (e.g. by persisting it onto the `GateTicket` record, per Task 9.1's
    `raiseGate`).

    If left `null` (the default), the module falls back to a Lambda-free placeholder/pass-through
    target: an `events:putEvents.waitForTaskToken` Task that publishes the same payload (including
    the task token) to the EventBridge bus named by `eventbridge_event_bus_name`. Wire a rule on
    that bus to a consumer (a Lambda, or the broker's own polling logic) to pick up the token. See
    this module's README for both wiring options.
  EOT
  type        = string
  default     = null
}

variable "eventbridge_event_bus_name" {
  description = "EventBridge bus name used for the placeholder notify target when notify_target_lambda_arn is null. Ignored otherwise."
  type        = string
  default     = "default"
}

variable "eventbridge_source" {
  description = "Event `Source` used for the placeholder EventBridge notify target when notify_target_lambda_arn is null. Ignored otherwise."
  type        = string
  default     = "daf.hitl"
}

variable "eventbridge_detail_type" {
  description = "Event `DetailType` used for the placeholder EventBridge notify target when notify_target_lambda_arn is null. Ignored otherwise."
  type        = string
  default     = "HitlGateRaised"
}

variable "task_timeout_seconds" {
  description = <<-EOT
    Optional `TimeoutSeconds` for the wait-for-task-token Task state. HITL gate waits are expected
    to be durable and long-lived (hours/days, per design.md Component 4), so this is left unset
    (`null`, no explicit timeout beyond the Standard workflow's own execution limits) by default.
    Set an explicit value only if a hard SLA on gate decisions is required.
  EOT
  type        = number
  default     = null
}

variable "task_heartbeat_seconds" {
  description = "Optional `HeartbeatSeconds` for the wait-for-task-token Task state. Unset (null) by default since Phase 1 has no gate-expiry policy yet (design.md notes EXPIRED is modeled but not populated in Phase 1)."
  type        = number
  default     = null
}

variable "logging_enabled" {
  description = "Whether to enable CloudWatch Logs execution logging for this state machine. Recommended on for HITL gate auditability."
  type        = bool
  default     = true
}

variable "log_retention_in_days" {
  description = "CloudWatch Logs retention for the state machine's execution log group. Ignored when logging_enabled = false."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
