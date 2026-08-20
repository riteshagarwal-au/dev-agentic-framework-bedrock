# bedrock-agentcore-memory

Provisions the single Amazon Bedrock AgentCore Memory resource used for per-run working memory
(short-term) and cross-run summarized recall (long-term), per Requirement 9.4 and design.md
"Knowledge & Memory — Phase 1" `MEM` node ("Bedrock AgentCore Memory (short + long term)").

## What this module creates

- An `awscc_bedrockagentcore_memory` resource (see "Provider version note" below for why this is
  an `awscc_*`, not `aws_*`, resource) configured with:
  - **Short-term retention** — `event_expiry_duration` (`var.event_expiry_duration`, default `7`
    days). AgentCore Memory does not expose a distinct "short-term" resource/knob separate from
    long-term — `event_expiry_duration` governs how long a run's raw working-memory events
    persist before AWS ages them out. Requirement 9.4's "per-run" framing is satisfied by keeping
    this window short relative to a run's lifetime and relying on `summarizeAndEvict` (Task 10.3)
    to have already extracted anything worth keeping into long-term memory records before that
    window elapses.
  - **Long-term memory strategies** — `memory_strategies` (`var.memory_strategies`), a list of
    built-in AgentCore strategies (`SEMANTIC`, `SUMMARIZATION`, `USER_PREFERENCE`, `EPISODIC`).
    Defaults to a single `SUMMARIZATION` strategy namespaced per run/session
    (`/summaries/{actorId}/{sessionId}`), directly satisfying Requirement 9.4's "summarized ...
    into AgentCore long-term memory rather than retained as a raw transcript" clause with zero
    extra configuration.
  - **Indexed metadata keys** — `indexed_keys` (`var.indexed_keys`), empty by default; add
    entries as agents adopt structured metadata filters on retrieval.
  - **Encryption** — optional `encryption_key_arn` (`var.encryption_key_arn`), null by default
    (AWS-owned key).
- An optional IAM **memory execution role** (`var.create_memory_execution_role`, default `false`)
  trusted by `bedrock-agentcore.amazonaws.com`, scoped via `aws:SourceAccount`/`aws:SourceArn` to
  this account's memories. Only needed if a strategy override is configured to invoke a specific
  Bedrock model on this memory's behalf — Phase 1's default strategy list does not need this, so
  it is off by default.
- A standalone **agent read/write access policy** (`var.create_agent_access_policy`, default
  `true`) — an `aws_iam_policy` scoped to this memory's ARN and a configurable
  read/write action list (`var.agent_read_actions` / `var.agent_write_actions`). This module does
  **not** attach the policy to any role itself; it only exposes `agent_memory_access_policy_arn`
  for Task 3.4's per-agent IAM roles to attach.

## How Task 10.3's `Memory.summarizeAndEvict` is expected to interact with this store

The post-invocation pipeline stage (Task 10.3) calls `Memory.summarizeAndEvict` after every
successful spoke agent invocation, and (per design.md's sequence diagram) again when a run
closes. Concretely, against this module's resources that means:

1. **During a run** — the pipeline calls `bedrock-agentcore:CreateEvent` (write) against
   `memory_arn` to append the invocation's compact result to the run's short-term working memory,
   scoped by `actorId` (the run/agent identity) and `sessionId` (the run ID).
2. **On run close** — the pipeline triggers AgentCore's asynchronous long-term extraction (which
   runs the configured `memory_strategies` — by default, `SUMMARIZATION` — over the accumulated
   short-term events) and then relies on `event_expiry_duration` to naturally age out the raw
   short-term events once the summary has been extracted, rather than deleting them itself. This
   is the "evict" half of summarize-and-evict: the *raw transcript* is not retained past the
   configured short-term window (Requirement 9.4), while the *summary* persists indefinitely as a
   long-term memory record.
3. **On subsequent runs / recall** — any agent needing prior context calls
   `bedrock-agentcore:RetrieveMemoryRecords` (semantic search) or `ListMemoryRecords`/
   `GetMemoryRecord` (direct lookup) against `memory_arn`, scoped to the strategy's namespace.

Task 10.3's implementation is responsible for the actual `CreateEvent`/`RetrieveMemoryRecords`
calls and for deciding what content to summarize — this module only provisions the Memory
resource, its strategies, and the IAM policy those calls run under. It does not implement
`Memory.summarizeAndEvict` itself.

## Usage

```hcl
module "bedrock_agentcore_memory" {
  source      = "../../modules/bedrock-agentcore-memory"
  environment = var.environment
}
```

```hcl
output "memory_id" {
  value = module.bedrock_agentcore_memory.memory_id
}

output "agent_memory_access_policy_arn" {
  value = module.bedrock_agentcore_memory.agent_memory_access_policy_arn
}
```

### Attaching to an agent's IAM role (Task 3.4)

```hcl
resource "aws_iam_role_policy_attachment" "discovery_agent_memory" {
  role       = module.discovery_agent_role.role_name
  policy_arn = module.bedrock_agentcore_memory.agent_memory_access_policy_arn
}
```

### Overriding strategies (adding semantic recall alongside summarization)

```hcl
module "bedrock_agentcore_memory" {
  source      = "../../modules/bedrock-agentcore-memory"
  environment = var.environment

  memory_strategies = [
    {
      type        = "SUMMARIZATION"
      name        = "RunSummarizer"
      description = "Summarizes a run's working memory on close."
      namespaces  = ["/summaries/{actorId}/{sessionId}"]
    },
    {
      type                = "SEMANTIC"
      name                = "FactExtractor"
      description         = "Extracts durable facts across runs."
      namespace_templates = ["/facts/{actorId}"]
    },
  ]
}
```

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; namespaces the memory name/tags. | `string` | n/a (required) |
| `name_prefix` | Prefix for the generated memory name. | `string` | `"daf-phase1"` |
| `memory_name` | Explicit memory name override (must match `^[a-zA-Z][a-zA-Z0-9_]{0,47}$` — underscores only, no hyphens). | `string` | `null` (derived) |
| `description` | Memory description. | `string` | Phase 1 default description |
| `event_expiry_duration` | Short-term event retention, in days (3–365). | `number` | `7` |
| `encryption_key_arn` | Optional KMS key for at-rest encryption. | `string` | `null` |
| `memory_strategies` | Long-term strategy list (`type`/`name`/`description`/`namespaces`/`namespace_templates`). | `list(object)` | one `SUMMARIZATION` strategy |
| `indexed_keys` | Metadata keys indexed for retrieval filtering. | `list(object)` | `[]` |
| `create_memory_execution_role` | Whether to create an IAM execution role for strategy model overrides. | `bool` | `false` |
| `memory_execution_role_arn` | Existing execution role ARN to use instead. | `string` | `null` |
| `create_agent_access_policy` | Whether to create the agent read/write IAM policy. | `bool` | `true` |
| `agent_read_actions` | Read actions granted by the agent access policy. | `list(string)` | Get/List/RetrieveMemoryRecords, GetEvent, ListEvents |
| `agent_write_actions` | Write actions granted by the agent access policy. | `list(string)` | CreateEvent, DeleteEvent |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `memory_id` | ID of the Memory resource. |
| `memory_arn` | ARN of the Memory resource. |
| `memory_name` | Name of the Memory resource. |
| `memory_status` | `CREATING`/`ACTIVE`/`DELETING`/`FAILED`. |
| `memory_execution_role_arn` | ARN of the created/passed-in execution role, or `null`. |
| `agent_memory_access_policy_arn` | ARN of the agent read/write IAM policy, or `null` if `create_agent_access_policy = false`. **Attach this to agent roles (Task 3.4)**, this module does not attach it itself. |
| `strategy_types_configured` | List of strategy types configured (e.g. `["SUMMARIZATION"]`). |

## Provider version note

**This is the one Phase 1 Terraform module that requires a second provider.** Every other module
under `infra/modules/` (`bedrock-guardrails`, `dynamodb-tables`, `state-backend`, etc.) only needs
`hashicorp/aws`. This module additionally requires `hashicorp/awscc` (the AWS Cloud Control
provider), pinned `~> 1.59` — see why below.

**What was checked:** the repo's pinned `hashicorp/aws` provider is `~> 5.0`, validated against
`5.100.0` (the version recorded in the root `.terraform.lock.hcl`). Running
`terraform providers schema -json` against that exact pinned version confirms it exposes **zero**
`aws_bedrockagentcore_*` resources — the entire `bedrockagentcore` service is absent from the
`~> 5.0` provider line. Bedrock AgentCore Memory support (`aws_bedrockagentcore_memory`,
`aws_bedrockagentcore_memory_strategy`) was only added to `hashicorp/aws` in **v6.18.0**
(per the upstream CHANGELOG), a full major version past this repo's `~> 5.0` ceiling. Upgrading
just for this one module would mean carrying a provider major-version bump (`~> 5.0` → `~> 6.0`)
for the entire root module and every other Phase 1 module that depends on `hashicorp/aws` — out
of scope for this task.

**What this module does instead:** rather than fabricate a `~> 5.0`-compatible resource that
doesn't exist, or ship an empty placeholder, this module uses `awscc_bedrockagentcore_memory`
from `hashicorp/awscc` (the AWS Cloud Control provider). This is a real, currently-shipping
resource — confirmed via `terraform providers schema -json` against `hashicorp/awscc ~> 1.59`
(the version installed, `1.98.0`) — that has provided AgentCore Memory support since
`awscc` **v1.59.0** (per the upstream CHANGELOG's "New Resource: `awscc_bedrockagentcore_memory`"
entry) and continues to receive feature updates (e.g. `indexed_keys`,
`stream_delivery_resources` in later releases). Both `terraform fmt` and `terraform validate`
pass cleanly against this module using that provider, including with non-default
`memory_strategies`, `indexed_keys`, and `create_memory_execution_role = true` configurations
(all exercised during development of this module).

**Tradeoff being flagged explicitly:** adding `hashicorp/awscc` as a second provider is a real
change to the project's provider surface — it has its own release cadence, its own
`terraform init`/lock-file entry, and (being schema-generated from AWS CloudFormation resource
types rather than hand-written like `hashicorp/aws`) a different day-to-day ergonomics/behavior
profile (e.g. `awscc` resources use Terraform's plugin-framework attribute-nested-type syntax —
`indexed_keys = [...]` as a plain attribute — rather than `hashicorp/aws`'s classic
`dynamic "block" { ... }` block syntax, which is why this module's `main.tf` sets
`indexed_keys` as a direct attribute assignment, not a `dynamic` block). If the project later
upgrades its root `hashicorp/aws` pin to `~> 6.0` anyway (e.g. for other reasons), this module
should be revisited and migrated to `aws_bedrockagentcore_memory`/`aws_bedrockagentcore_
memory_strategy` to drop the second provider dependency — until then, `awscc` is the only way to
get a real (non-fabricated) Terraform resource for this service against this repo's currently
pinned `hashicorp/aws` version.

**Root-level wiring required once this module is instantiated:** the root module's
`infra/versions.tf`/`infra/providers.tf` will need an `awscc` entry in `required_providers` and a
corresponding `provider "awscc" { region = var.aws_region }` block (mirroring the existing `aws`
provider block) before `module "bedrock_agentcore_memory" { source = "../../modules/
bedrock-agentcore-memory" ... }` can be wired into `infra/main.tf` — this module's own
`versions.tf` declares the `awscc` requirement for standalone validation, but does not (per
convention) declare a `provider` block itself.

## Requirements traceability

- Requirement 9.4: "WHEN a run closes THEN the working memory for that run SHALL be summarized
  and evicted into AgentCore long-term memory rather than retained as a raw transcript." — this
  module provisions the Memory resource, its short-term retention window
  (`event_expiry_duration`), and its long-term summarization strategy; Task 10.3's
  `Memory.summarizeAndEvict` implementation is responsible for actually making the
  `CreateEvent`/extraction/`RetrieveMemoryRecords` calls this module's IAM policy authorizes.
