# bedrock-guardrails

Provisions the single Amazon Bedrock Guardrail applied to **every** agent's Bedrock model calls in
DAF Phase 1, per Requirement 9.3 and the design.md "Knowledge & Memory — Phase 1" `GUARD` node
("Bedrock Guardrails (all agents)").

## What this module creates

- An `aws_bedrock_guardrail` resource configured with:
  - **Content policy** (`content_policy_config`) — a `PROMPT_ATTACK` filter (prompt-injection /
    jailbreak defense, `input_strength = HIGH`) plus the standard harmful-content categories
    (hate, insults, misconduct, sexual, violence) at `MEDIUM` strength by default.
  - **Sensitive information policy** (`sensitive_information_policy_config`) — PII entity
    filters (`var.pii_entities`, default: name, email, phone, SSN, credit/debit card, AWS access
    key, AWS secret key, password, IP address, username) with a default `ANONYMIZE` action, plus
    optional custom regex filters (`var.pii_regexes`).
  - **Topic policy** (`topic_policy_config`) — denied topics (`var.denied_topics`), defaulted to a
    Phase 1 list of topics irrelevant to a cloud-migration assistant (investment/legal/medical
    advice, unrelated creative-writing requests, credential/secret-disclosure attempts). The exact
    denied-topic set is a policy decision — override `var.denied_topics` to change it without
    editing the module.
  - **Word policy** (`word_policy_config`) — managed word lists (`var.managed_word_lists`,
    default: `PROFANITY`) plus optional custom denied words/phrases (`var.denied_words`).
  - **Contextual grounding policy** (`contextual_grounding_policy_config`) — `GROUNDING` and
    `RELEVANCE` filters at configurable thresholds (`var.grounding_threshold`,
    `var.relevance_threshold`, both default `0.75`), covering Requirement 9.3's "grounding
    checks" clause.
- An `aws_bedrock_guardrail_version` resource (when `var.create_published_version = true`, the
  default) that publishes an immutable, numbered version of the guardrail. Consumers should
  reference this published version rather than the mutable `DRAFT` working copy, so an in-progress
  edit to the guardrail's configuration never changes behavior for a run already in flight.

## Why a published version, not DRAFT

Bedrock Guardrails always has a `DRAFT` working copy that reflects the latest `aws_bedrock_guardrail`
configuration. Editing the guardrail (e.g. adding a denied topic) mutates `DRAFT` immediately.
Publishing a version (`aws_bedrock_guardrail_version`) snapshots that configuration into an
immutable, numbered version. Agents and the pre-invocation hook should pin to
`guardrail_published_version`, not `DRAFT`, so:

- A guardrail config change doesn't retroactively alter the safety behavior of an in-flight run.
- Rolling forward to a new guardrail version is an explicit, reviewable change (new module apply +
  updated agent wiring), not an implicit side effect of any guardrail edit.

## How this module is consumed downstream

- **Task 13.7 (Bedrock Agent resources)**: each core agent's `aws_bedrockagent_agent` (or
  equivalent) resource attaches this guardrail via `guardrail_configuration { guardrail_identifier
  = module.bedrock_guardrails.guardrail_id, guardrail_version =
  module.bedrock_guardrails.guardrail_published_version }`, so every agent's model calls pass
  through the same guardrail without per-agent duplication.
- **Task 10.1 (pre-invocation hook `attachGuardrails`)**: the hook pipeline's `attachGuardrails`
  step references this same `guardrail_id` / `guardrail_published_version` pair (via
  configuration, e.g. an environment variable or SSM parameter populated from this module's
  outputs) when invoking the Bedrock Agents/Models runtime, guaranteeing the pipeline enforces the
  identical guardrail the agent resource itself is configured with. This module does not create
  that config plumbing — it only exposes the stable IDs Task 10.1's implementation reads.

## Usage

```hcl
module "bedrock_guardrails" {
  source      = "../../modules/bedrock-guardrails"
  environment = var.environment
}
```

```hcl
output "guardrail_id" {
  value = module.bedrock_guardrails.guardrail_id
}

output "guardrail_published_version" {
  value = module.bedrock_guardrails.guardrail_published_version
}
```

### Overriding denied topics

```hcl
module "bedrock_guardrails" {
  source      = "../../modules/bedrock-guardrails"
  environment = var.environment

  denied_topics = [
    {
      name       = "competitor_products"
      definition = "Requests to compare or recommend competitor cloud providers' products over the target AWS architecture."
      examples   = ["Why not just use GCP instead?"]
    },
  ]
}
```

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; namespaces the guardrail name/tags. | `string` | n/a (required) |
| `name_prefix` | Prefix for the generated guardrail name. | `string` | `"daf-phase1"` |
| `guardrail_name` | Explicit guardrail name override. | `string` | `null` (derived) |
| `description` | Guardrail description. | `string` | Phase 1 default description |
| `blocked_input_messaging` | Message returned when an input prompt is blocked. | `string` | default message |
| `blocked_outputs_messaging` | Message returned when a model response is blocked. | `string` | default message |
| `kms_key_arn` | Optional KMS key for at-rest encryption. | `string` | `null` |
| `content_filters` | Content policy filter list (type/strength/enabled per category). | `list(object)` | prompt-attack + harmful-content defaults |
| `pii_entities` | PII entity types to redact and their action. | `list(object)` | 10-entity default list, `ANONYMIZE` |
| `pii_regexes` | Custom regex-based sensitive-information filters. | `list(object)` | `[]` |
| `denied_topics` | Denied-topic definitions. | `list(object)` | Phase 1 default 5-topic list |
| `managed_word_lists` | Managed word list types to enable. | `list(string)` | `["PROFANITY"]` |
| `denied_words` | Custom denied words/phrases. | `list(string)` | `[]` |
| `grounding_threshold` | Minimum grounding score (0.0-1.0). | `number` | `0.75` |
| `relevance_threshold` | Minimum relevance score (0.0-1.0). | `number` | `0.75` |
| `create_published_version` | Whether to publish an immutable guardrail version. | `bool` | `true` |
| `guardrail_version_description` | Description recorded on the published version. | `string` | default description |
| `skip_destroy_on_new_version` | Retain the previous published version on a future apply. | `bool` | `true` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `guardrail_id` | ID of the guardrail (stable across versions). |
| `guardrail_arn` | ARN of the guardrail. |
| `guardrail_draft_version` | Version string of the mutable working copy (always `"DRAFT"`). |
| `guardrail_published_version` | Numbered version published by this module, or `null` if `create_published_version = false`. **Use this for agent/hook wiring, not `guardrail_draft_version`.** |
| `guardrail_status` | `READY` or `FAILED`. |

## Provider version note

This module uses the `aws_bedrock_guardrail` and `aws_bedrock_guardrail_version` resources from
the `hashicorp/aws` provider. Both resources exist in provider `~> 5.0` releases (validated
against `5.100.0`, the version pinned in the root `.terraform.lock.hcl`) — **no provider version
bump is required** for this module to `terraform validate`/`plan` successfully.

One capability gap was found and designed around: independent per-input/per-output
`action`/`enabled` toggles on `content_policy_config.filters_config`,
`sensitive_information_policy_config.pii_entities_config`,
`sensitive_information_policy_config.regexes_config`, and `word_policy_config.*` were only added
in AWS provider **v6.x** (per the upstream CHANGELOG: `input_action`/`output_action`/
`input_enabled`/`output_enabled` arguments). Provider `5.100.0` only supports the coarser
pre-v6 schema:

- `content_policy_config.filters_config`: `type`, `input_strength`, `output_strength` only (no
  per-direction enable toggle — both input and output are always evaluated for every filter).
- `sensitive_information_policy_config.pii_entities_config` /  `regexes_config`: a single
  `action` (or `action`/`name`/`pattern`/`description`) applied uniformly, not split into
  `input_action`/`output_action`.
- `word_policy_config.managed_word_lists_config` / `words_config`: `type`/`text` only, no
  per-direction toggle.

This module's `variables.tf` is intentionally scoped to that v5-compatible schema. **If the
project upgrades to AWS provider v6.x**, this module can be extended to accept the finer-grained
`input_action`/`output_action`/`input_enabled`/`output_enabled` controls per policy config block —
until then, the coarser v5 schema is what `terraform validate` accepts and is what's implemented
here.

## Requirements traceability

- Requirement 9.3: "EVERY Bedrock model call made by any agent SHALL pass through Bedrock
  Guardrails (PII redaction, prompt-injection defense, denied topics, grounding checks)." — this
  module provisions that guardrail; Task 13.7 and Task 10.1 are responsible for actually attaching
  it to every agent's model calls (this module alone does not enforce attachment).
