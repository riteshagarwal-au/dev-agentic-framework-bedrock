data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  use_lambda_target = var.notify_target_lambda_arn != null

  # ---------------------------------------------------------------------------
  # ASL definition (design.md Component 4 / Algorithm 3 raiseGate):
  #
  #   A single Task state starts, immediately pauses using the "wait for task
  #   token" pattern, and does not transition ("End": true is unreachable in
  #   practice — the execution only ever leaves this state via SendTaskSuccess
  #   or SendTaskFailure from decide(), Task 9.2). The gate/run/ticket
  #   identifiers passed into startExecution's input are forwarded verbatim to
  #   the notify target alongside the task token ($$.Task.Token), so whatever
  #   receives the notification (Lambda or EventBridge) can correlate the
  #   token back to the GateTicket that is waiting on it.
  #
  #   Two notify-target shapes are supported (see variables.tf):
  #     - notify_target_lambda_arn set    -> lambda:invoke.waitForTaskToken
  #     - notify_target_lambda_arn null   -> events:putEvents.waitForTaskToken
  #                                           (placeholder/pass-through target;
  #                                           no Lambda required to exist yet)
  # ---------------------------------------------------------------------------
  wait_state_resource = local.use_lambda_target ? "arn:${data.aws_partition.current.partition}:states:::lambda:invoke.waitForTaskToken" : "arn:${data.aws_partition.current.partition}:states:::events:putEvents.waitForTaskToken"

  # Built as two independently-shaped locals (rather than one ternary'd map) because the Lambda
  # and EventBridge Parameters shapes have different keys, and Terraform requires both branches of
  # a conditional to share a single consistent type.
  wait_state_parameters_lambda = {
    FunctionName = var.notify_target_lambda_arn
    Payload = {
      "taskToken.$" = "$$.Task.Token"
      "gate.$"      = "$.gate"
      "runId.$"     = "$.runId"
      "ticketId.$"  = "$.ticketId"
      "context.$"   = "$.context"
    }
  }

  wait_state_parameters_eventbridge = {
    Entries = [
      {
        EventBusName = var.eventbridge_event_bus_name
        Source       = var.eventbridge_source
        DetailType   = var.eventbridge_detail_type
        "Detail.$"   = "States.JsonToString($)"
      }
    ]
  }

  wait_state_common = {
    Type     = "Task"
    Resource = local.wait_state_resource
    End      = true
  }

  wait_state_optional = merge(
    var.task_timeout_seconds != null ? { TimeoutSeconds = var.task_timeout_seconds } : {},
    var.task_heartbeat_seconds != null ? { HeartbeatSeconds = var.task_heartbeat_seconds } : {}
  )

  state_machine_definition = local.use_lambda_target ? jsonencode({
    Comment = "DAF HITL gate wait/resume broker (design.md Component 4). Starts, notifies, and pauses holding a task token until decide() (Task 9.2) calls SendTaskSuccess or SendTaskFailure against that token. Expected startExecution input: { \"gate\": <HitlGateType>, \"runId\": <RunId>, \"ticketId\": <GateTicketId>, \"context\": <ApprovalContext> }."
    StartAt = "WaitForHitlDecision"
    States = {
      WaitForHitlDecision = merge(local.wait_state_common, {
        Parameters = local.wait_state_parameters_lambda
      }, local.wait_state_optional)
    }
    }) : jsonencode({
    Comment = "DAF HITL gate wait/resume broker (design.md Component 4). Starts, notifies, and pauses holding a task token until decide() (Task 9.2) calls SendTaskSuccess or SendTaskFailure against that token. Expected startExecution input: { \"gate\": <HitlGateType>, \"runId\": <RunId>, \"ticketId\": <GateTicketId>, \"context\": <ApprovalContext> }."
    StartAt = "WaitForHitlDecision"
    States = {
      WaitForHitlDecision = merge(local.wait_state_common, {
        Parameters = local.wait_state_parameters_eventbridge
      }, local.wait_state_optional)
    }
  })
}

# ---------------------------------------------------------------------------
# IAM role assumed by the state machine itself, to invoke the notify target
# (Lambda or EventBridge PutEvents). This is distinct from — and unrelated
# to — the HITL Broker's own IAM role/policy for resuming executions
# (aws_iam_policy.hitl_broker_send_task below).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "state_machine_execution" {
  name               = "${var.state_machine_name}-sfn-exec"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.state_machine_name}-sfn-exec"
  })
}

data "aws_iam_policy_document" "sfn_invoke_target" {
  dynamic "statement" {
    for_each = local.use_lambda_target ? [1] : []
    content {
      sid       = "InvokeNotifyLambda"
      effect    = "Allow"
      actions   = ["lambda:InvokeFunction"]
      resources = [var.notify_target_lambda_arn]
    }
  }

  dynamic "statement" {
    for_each = local.use_lambda_target ? [] : [1]
    content {
      sid       = "PutNotifyEvent"
      effect    = "Allow"
      actions   = ["events:PutEvents"]
      resources = ["arn:${data.aws_partition.current.partition}:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:event-bus/${var.eventbridge_event_bus_name}"]
    }
  }
}

resource "aws_iam_role_policy" "sfn_invoke_target" {
  name   = "${var.state_machine_name}-invoke-notify-target"
  role   = aws_iam_role.state_machine_execution.id
  policy = data.aws_iam_policy_document.sfn_invoke_target.json
}

resource "aws_iam_role_policy" "sfn_logging" {
  count = var.logging_enabled ? 1 : 0

  name = "${var.state_machine_name}-logging"
  role = aws_iam_role.state_machine_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StateMachineLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch Logs group for state machine execution history (audit trail
# support — design.md Component 4 / Requirement 5.3 "every decision written
# to the audit log").
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "state_machine" {
  count = var.logging_enabled ? 1 : 0

  name              = "/aws/states/${var.state_machine_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(var.tags, {
    Name = "${var.state_machine_name}-logs"
  })
}

# ---------------------------------------------------------------------------
# The state machine itself: a single "wait for task token" Task state.
# ---------------------------------------------------------------------------

resource "aws_sfn_state_machine" "hitl_gate" {
  name       = var.state_machine_name
  role_arn   = aws_iam_role.state_machine_execution.arn
  definition = local.state_machine_definition
  type       = "STANDARD"

  dynamic "logging_configuration" {
    for_each = var.logging_enabled ? [1] : []
    content {
      log_destination        = "${aws_cloudwatch_log_group.state_machine[0].arn}:*"
      include_execution_data = true
      level                  = "ALL"
    }
  }

  tags = merge(var.tags, {
    Name = var.state_machine_name
  })

  depends_on = [aws_iam_role_policy.sfn_logging]
}

# ---------------------------------------------------------------------------
# HITL Broker resume permissions.
#
# `states:SendTaskSuccess` / `states:SendTaskFailure` are Activity-level-style
# permissions keyed by the *task token* the caller already holds, not by
# state machine ARN — AWS does not support resource-level scoping for these
# two actions (they only accept Resource = "*"; see AWS's "Creating granular
# permissions for non-admin users in Step Functions" guide). This is a
# documented AWS API limitation, not a design choice here: the token itself
# (obtained only via this state machine's own raiseGate → NOTIFY_PORTAL flow,
# never handed out any other way) is what scopes the ability to actually
# resume a *specific* held execution. The policy below is therefore scoped to
# exactly the two actions the broker's decide() needs and nothing else — no
# StartExecution, no DescribeStateMachine, no admin actions — which is the
# tightest scoping IAM allows for this API pair.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "hitl_broker_send_task" {
  statement {
    sid    = "HitlBrokerResumeGateWait"
    effect = "Allow"
    actions = [
      "states:SendTaskSuccess",
      "states:SendTaskFailure",
    ]
    # Resource-level scoping to a specific state machine ARN is not supported by
    # AWS for these two actions; Resource must be "*". See comment above.
    resources = ["*"]
  }
}

resource "aws_iam_policy" "hitl_broker_send_task" {
  name        = "${var.state_machine_name}-send-task-result"
  description = "Grants states:SendTaskSuccess/SendTaskFailure only, for the HITL Broker's decide() (Task 9.2) to resume a held ${var.state_machine_name} execution via its task token."
  policy      = data.aws_iam_policy_document.hitl_broker_send_task.json

  tags = merge(var.tags, {
    Name = "${var.state_machine_name}-send-task-result"
  })
}
