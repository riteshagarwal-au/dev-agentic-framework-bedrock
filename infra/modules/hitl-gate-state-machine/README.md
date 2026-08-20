# hitl-gate-state-machine

Provisions the AWS Step Functions state machine that brokers the "wait for task token" pause/resume
mechanism for the HITL Approval Broker, per design.md "Component 4: HITL Approval Broker" and
Requirement 5.2.

## Why this exists

A HITL gate wait is a durable, long-lived pause (hours to days). The hook pipeline runs on Lambda,
which cannot hold a blocking call open for that duration. Step Functions is used here *narrowly* —
scoped only to brokering the wait/resume itself:

- `raiseGate` (Task 9.1, Python) calls `StepFunctions.start_execution` against this state machine.
  The execution immediately enters its one Task state and pauses, holding a **task token**.
- `decide` (Task 9.2, Python) calls `StepFunctions.send_task_success` or `send_task_failure` against
  that held token to resume (or fail) the paused execution.

This is not a general orchestration replacement. Durable run state (`RunState`, `RunCounters`,
`GateTicket`) is still persisted in DynamoDB (Task 5.x) — that decision is unchanged. Step Functions
exists solely to hold the "someone needs to wake this pipeline up later" concern that a stateless
Lambda invocation cannot hold on its own.

## What this module creates

- `aws_sfn_state_machine.hitl_gate` — a `STANDARD` state machine with exactly one state,
  `WaitForHitlDecision`, a `Task` state using the `.waitForTaskToken` integration pattern. It never
  transitions on its own; the only ways out are `SendTaskSuccess` or `SendTaskFailure` called by
  `decide()` against the token this state holds.
- An IAM role + policy for the **state machine's own execution** (to invoke whatever notify target
  is configured — see below). This is unrelated to the HITL Broker's own runtime role.
- `aws_iam_policy.hitl_broker_send_task` — a **standalone** policy scoped to exactly
  `states:SendTaskSuccess` and `states:SendTaskFailure`, intended to be attached to the HITL
  Broker's own IAM role (Task 3.4 / Task 9.2's runtime identity) by the caller. This module does not
  attach it to anything, since it does not own the broker's role.
- Optionally (default on), a CloudWatch Logs group with `ALL`-level execution logging enabled on the
  state machine, supporting the audit trail requirement (every gate decision must be traceable).

## Notify target: two supported shapes

The single Task state needs *something* to notify when a gate is raised (e.g. to post to the portal,
Slack, email — whatever surfaces the pending ticket to a human, per design.md "surfaced to the
portal"). Task 2.4 does not implement that notifier; it only wires the state machine to call it.

1. **Lambda target** (`notify_target_lambda_arn` set): the Task state uses
   `arn:aws:states:::lambda:invoke.waitForTaskToken`, invoking the given Lambda with:
   ```json
   {
     "taskToken": "<the held task token>",
     "gate": "<HitlGateType from startExecution input>",
     "runId": "<RunId from startExecution input>",
     "ticketId": "<GateTicketId from startExecution input>",
     "context": "<ApprovalContext from startExecution input>"
   }
   ```
   The Lambda's job (implemented elsewhere, not by this module) is to make that token available to
   the broker — e.g. by writing it onto the `GateTicket.stepFunctionsTaskToken` field per Task 9.1's
   `raiseGate`, and/or triggering the actual human-facing notification.

2. **EventBridge placeholder target** (`notify_target_lambda_arn` left `null`, the default): the Task
   state uses `arn:aws:states:::events:putEvents.waitForTaskToken` instead, publishing an event with
   the same payload shape (JSON-stringified via the `States.JsonToString` intrinsic function) to the
   bus named by `eventbridge_event_bus_name` (default `"default"`), with `Source` /
   `DetailType` set from `eventbridge_source` / `eventbridge_detail_type`. This lets the state machine
   be created and validated before any notify-Lambda exists — wire an EventBridge rule on that bus to
   whatever consumer picks up the token when ready, or switch to the Lambda target later by setting
   `notify_target_lambda_arn`.

Either way, **the task token itself is the durable handle** — nothing about `raiseGate`/`decide`
depends on which notify shape is wired.

## Expected `startExecution` input shape

The Python HITL broker's `raiseGate` (Task 9.1) is expected to call:

```python
response = stepfunctions_client.start_execution(
    stateMachineArn=state_machine_arn,   # this module's state_machine_arn output
    name=ticket_id,                      # recommended: use ticketId as the execution name for easy lookup
    input=json.dumps({
        "gate": gate_type,        # one of the 7 HitlGateType values (design.md Component 4 / source §8)
        "runId": run_id,
        "ticketId": ticket_id,
        "context": approval_context,   # ApprovalContext: artifact refs + summary for the human
    }),
)
```

`start_execution` returns immediately with an `executionArn` (Standard workflows do not return the
task token directly). The task token itself only becomes available to whatever the notify target is
(via `$$.Task.Token`), which is why `raiseGate` must persist the `GateTicket` and rely on the notify
target (Lambda or EventBridge consumer) to write `stepFunctionsTaskToken` onto the ticket before
`decide()` can resume it — per Algorithm 3 in design.md, `raiseGate` returns once the ticket is
persisted; it does not itself block waiting for the token.

## How `decide()` resumes the execution

Task 9.2's `decide(ticketId, decision, approver)`:

```python
if decision == "APPROVED":
    stepfunctions_client.send_task_success(
        taskToken=ticket.step_functions_task_token,
        output=json.dumps({"result": "APPROVED"}),
    )
else:
    stepfunctions_client.send_task_failure(
        taskToken=ticket.step_functions_task_token,
        error="HitlGateRejected",
        cause=f"HITL gate rejected: {ticket.gate_type}",
    )
```

## IAM scoping note: why `send_task_result_policy_arn` uses `Resource = "*"`

`states:SendTaskSuccess` and `states:SendTaskFailure` are **not** state-machine-scoped actions in
AWS IAM — they identify the target execution purely by the task token passed in the API call, and
AWS does not support restricting these two actions to a specific state machine ARN (the API requires
`Resource = "*"`; see AWS's ["Creating granular permissions for non-admin users in Step
Functions"](https://docs.aws.amazon.com/step-functions/latest/dg/concept-create-iam-advanced.html)).
This is a documented AWS API limitation, not a design choice made here.

Given that, the policy this module outputs is scoped as tightly as IAM allows: exactly these two
actions, nothing else (no `StartExecution`, `DescribeStateMachine`, or other Step Functions
permissions). The practical scoping to *this specific* state machine's executions comes from the
task token itself — a token can only be obtained by whatever receives this module's notify-target
payload (the Lambda or EventBridge consumer wired per above), which only ever fires for executions of
*this* state machine.

Attach `send_task_result_policy_arn` to the HITL Broker's IAM role (Task 3.4) via
`aws_iam_role_policy_attachment` in the composing module/root — this module does not own that role
and does not attach anything to it itself.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `state_machine_name` | Name of the state machine. | `string` | `"daf-hitl-gate"` |
| `notify_target_lambda_arn` | ARN of a notify Lambda to invoke with `.waitForTaskToken`. Leave `null` to use the EventBridge placeholder target instead. | `string` | `null` |
| `eventbridge_event_bus_name` | Bus name for the EventBridge placeholder target. Ignored if `notify_target_lambda_arn` is set. | `string` | `"default"` |
| `eventbridge_source` | Event `Source` for the EventBridge placeholder target. Ignored if `notify_target_lambda_arn` is set. | `string` | `"daf.hitl"` |
| `eventbridge_detail_type` | Event `DetailType` for the EventBridge placeholder target. Ignored if `notify_target_lambda_arn` is set. | `string` | `"HitlGateRaised"` |
| `task_timeout_seconds` | Optional `TimeoutSeconds` on the wait state. Left unset by default — Phase 1 has no gate-expiry policy. | `number` | `null` |
| `task_heartbeat_seconds` | Optional `HeartbeatSeconds` on the wait state. | `number` | `null` |
| `logging_enabled` | Enable CloudWatch Logs execution logging. | `bool` | `true` |
| `log_retention_in_days` | Log group retention. Ignored if `logging_enabled = false`. | `number` | `90` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `state_machine_arn` | ARN to pass to `start_execution` from `raiseGate`. |
| `state_machine_name` | Name of the state machine. |
| `state_machine_execution_role_arn` | Role the state machine itself assumes (to call the notify target) — not the broker's role. |
| `send_task_result_policy_arn` | ARN of the standalone `SendTaskSuccess`/`SendTaskFailure`-only policy to attach to the HITL Broker's role. |
| `send_task_result_policy_document` | The same policy as raw JSON, for callers that prefer to inline/merge it. |
| `log_group_name` | CloudWatch Logs group name (`null` if `logging_enabled = false`). |

## Requirements traceability

- Requirement 5.2: "...the system SHALL call `raiseGate(gate, runId, context)`, which SHALL start an
  AWS Step Functions execution that pauses using the 'wait for task token' pattern, and SHALL block
  that action until the resulting ticket is resolved via `decide()` calling `SendTaskSuccess` or
  `SendTaskFailure` against the held task token... no Lambda invocation SHALL hold a blocking call
  open for the duration of the wait." — this module is the state machine referenced by that
  requirement; the single `.waitForTaskToken` Task state is exactly the mechanism, and no component
  here (or in the Python `raiseGate`/`decide` code that calls it) ever holds a synchronous/blocking
  call open across the wait.
