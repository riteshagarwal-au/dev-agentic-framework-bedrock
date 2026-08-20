# bedrock-knowledge-base

Provisions the DAF Phase 1 corporate Knowledge Base — Bedrock KB backed by an S3 data source and
the **S3 Vectors** vector store — per Requirement 9.1 and design.md §6.1.1 ("Corporate KB —
Bedrock KB on S3 + S3 Vectors (authoritative)").

> Requirement 9.1: "WHEN an agent needs corporate guidance THEN it SHALL retrieve top-k chunks
> (not the whole KB) from the Bedrock Knowledge Base backed by S3 and the S3 Vectors vector
> store."

## What this module creates

- An S3 bucket holding the corporate KB's source documents (create-or-reuse via
  `var.create_source_bucket` / `var.existing_source_bucket_arn`, mirroring `state-backend`'s
  `create_kms_key` pattern), versioned, encrypted (SSE-S3 by default, SSE-KMS if
  `var.kms_key_arn` is set), with public access fully blocked and bucket-owner-enforced
  ownership.
- An **S3 Vectors vector bucket** (`awscc_s3vectors_vector_bucket`) and **vector index**
  (`awscc_s3vectors_index`) — the Phase 1 KB vector store — also create-or-reuse via
  `var.create_vector_resources` / `var.existing_vector_bucket_arn` /
  `var.existing_vector_index_arn`.
- A Bedrock **Knowledge Base** (`awscc_bedrock_knowledge_base`) of `knowledge_base_configuration.type
  = "VECTOR"`, configured with `storage_configuration.type = "S3_VECTORS"` pointing at the vector
  bucket/index above, and a Bedrock embedding model (Titan Text Embeddings V2 by default,
  `var.embedding_model_id`/`var.embedding_model_arn`).
- A Bedrock **S3 data source** (`awscc_bedrock_data_source`) attached to the knowledge base,
  pointing at the KB source bucket, with a configurable chunking strategy
  (`var.chunking_strategy`, defaulting to `FIXED_SIZE` per Phase 1 defaults).
- An IAM **Knowledge Base service role** (`bedrock.amazonaws.com` principal), named per Bedrock's
  required `AmazonBedrockExecutionRoleForKnowledgeBase_` prefix, scoped to exactly:
  - Read/list on this KB's S3 source bucket only (optionally under
    `var.source_bucket_inclusion_prefix`).
  - `bedrock:InvokeModel` on this KB's embedding model only.
  - Read/write S3 Vectors data-plane actions on this KB's vector bucket/index only.
  - `kms:Decrypt` on `var.kms_key_arn`, only if set.

## Why the KB, data source, and S3 Vectors resources are `awscc_*`, not `aws_*`

**What was checked:** running `terraform providers schema -json` against the repo's pinned
`hashicorp/aws` provider (`~> 5.0`, validated at `5.100.0`, the version recorded in the root
`.terraform.lock.hcl`) shows:

- **Zero** `aws_s3vectors_*` resources exist in that provider version at all — S3 Vectors support
  (`aws_s3vectors_vector_bucket`, `aws_s3vectors_index`) was only added to `hashicorp/aws` in
  **v6.24.0**, a full major version past this repo's `~> 5.0` ceiling.
- `aws_bedrockagent_knowledge_base.storage_configuration` only supports
  `opensearch_serverless_configuration`, `pinecone_configuration`, `rds_configuration`, and
  `redis_enterprise_cloud_configuration` as vector-store backends in `5.100.0` — there is no
  `s3_vectors_configuration` option. That option (`s3_vectors_configuration` block plus
  `storage_configuration.type = "S3_VECTORS"`) was only added to `hashicorp/aws` in **v6.27.0**.

Declaring `aws_bedrockagent_knowledge_base` with any of the four `5.100.0`-supported backends
would not be "the KB backed by S3 and the S3 Vectors vector store" that Requirement 9.1 and
design.md §6.1.1 call for — OpenSearch Serverless in particular is explicitly out of scope for
Phase 1 per requirements.md's "Out of Scope for Phase 1" list. Substituting it here would
silently violate that scope boundary rather than honor it.

**What this module does instead:** following the precedent set by Task 3.3's
`bedrock-agentcore-memory` module (which faced the identical "the feature doesn't exist yet in
our pinned `hashicorp/aws` line" situation for AgentCore Memory), this module uses four real,
currently-shipping resources from `hashicorp/awscc` (the AWS Cloud Control provider, already a
project dependency since Task 3.3, pinned `~> 1.59`, validated at `1.98.0`):

| Resource | Purpose |
|---|---|
| `awscc_s3vectors_vector_bucket` | The S3 Vectors vector bucket. |
| `awscc_s3vectors_index` | The vector index within that bucket (dimension, distance metric, data type). |
| `awscc_bedrock_knowledge_base` | The Knowledge Base itself, `storage_configuration.type = "S3_VECTORS"` pointing at the vector bucket/index above (`s3_vectors_configuration.vector_bucket_arn`/`index_arn`/`index_name`) and `knowledge_base_configuration.type = "VECTOR"` with a `vector_knowledge_base_configuration.embedding_model_arn`. |
| `awscc_bedrock_data_source` | The S3 data source attached to the knowledge base, with `data_source_configuration.type = "S3"` and a `vector_ingestion_configuration.chunking_configuration`. |

All four were confirmed via `terraform providers schema -json` against the installed
`hashicorp/awscc 1.98.0` to have the exact `S3_VECTORS`/`s3_vectors_configuration` schema this
module uses (cross-checked against AWS's `AWS::Bedrock::KnowledgeBase`,
`AWS::Bedrock::DataSource`, `AWS::S3Vectors::VectorBucket`, and `AWS::S3Vectors::Index`
CloudFormation resource-type documentation, since CloudFormation resource-type schemas are what
`awscc` resources are generated from). `terraform fmt` and `terraform validate` pass cleanly
against this module with both providers wired in, and `terraform plan` (against sandbox AWS
credentials, no real S3 Vectors/Bedrock KB service calls made) resolves the full 11-resource
graph — including the `S3_VECTORS`/`s3_vectors_configuration` block — with no schema errors, for
both the create-everything default path and the create-or-reuse (`create_source_bucket = false`,
`create_vector_resources = false`) path.

**No placeholder scaffolding was needed for this module** — unlike some other Phase 1 modules
that hit a genuine capability gap with no real resource available in either provider, S3 Vectors
+ Bedrock KB support does exist today, just not in `hashicorp/aws ~> 5.0`. This module declares
the real thing instead of a stand-in.

**Tradeoff being flagged explicitly:** this module now shares Task 3.3's tradeoff of depending on
`hashicorp/awscc` in addition to `hashicorp/aws` — a second provider with its own release cadence
and (being schema-generated from AWS CloudFormation resource types) different day-to-day
ergonomics from hand-written `hashicorp/aws` resources (e.g. `tags` on `awscc_bedrock_knowledge_base`
is a plain `map(string)`, but `tags` on `awscc_s3vectors_vector_bucket`/`awscc_s3vectors_index` is
a `set` of `{ key, value }` objects — reflected in this module's `main.tf` building that shape
directly for the two S3 Vectors resources rather than reusing `local.tags` as-is). Because
`bedrock-agentcore-memory` (Task 3.3) already added `hashicorp/awscc ~> 1.59` as a project
dependency, this module does not introduce a *new* provider to the project — it reuses the one
Task 3.3 already added. If the project later upgrades its root `hashicorp/aws` pin to `~> 6.27`
or newer anyway, this module should be revisited and migrated to
`aws_bedrockagent_knowledge_base`/`aws_bedrockagent_data_source`/`aws_s3vectors_vector_bucket`/
`aws_s3vectors_index` to drop the cross-provider composition — until then, `awscc` is what
provides real (non-fabricated) Terraform resources for the S3 Vectors backend against this repo's
currently pinned `hashicorp/aws` version.

**Root-level wiring required once this module is instantiated:** same as Task 3.3 — the root
module's `infra/versions.tf`/`infra/providers.tf` need an `awscc` entry in `required_providers`
and a `provider "awscc" { region = var.aws_region }` block before
`module "bedrock_knowledge_base" { source = "../../modules/bedrock-knowledge-base" ... }` can be
wired into `infra/main.tf`. If Task 3.3 has already been wired into the root module, this
requirement is already satisfied and no further root-level change is needed.

## KB service role naming constraint

Bedrock enforces that a knowledge base's `role_arn` begins with the literal prefix
`AmazonBedrockExecutionRoleForKnowledgeBase_` (the schema description for
`awscc_bedrock_knowledge_base.role_arn` states this explicitly; it mirrors the same
`AmazonBedrockExecutionRoleForAgents_` prefix requirement documented for Bedrock Agents' service
role). IAM role names are capped at 64 characters and the required prefix alone is 43 characters,
leaving only 21 characters for a suffix — too tight to reuse this module's full
`<name_prefix>-corporate-kb-<environment>` KB name. This module defaults the role name to
`AmazonBedrockExecutionRoleForKnowledgeBase_<name_prefix>-<environment>` (via
`var.kb_role_name_suffix`) and validates both the derived and any explicitly-supplied
`var.kb_role_name` against the 64-character limit and required prefix at plan time.

## Usage

```hcl
module "bedrock_knowledge_base" {
  source      = "../../modules/bedrock-knowledge-base"
  environment = var.environment
}
```

```hcl
output "knowledge_base_id" {
  value = module.bedrock_knowledge_base.knowledge_base_id
}

output "knowledge_base_arn" {
  value = module.bedrock_knowledge_base.knowledge_base_arn
}
```

### Reusing an existing source bucket and vector bucket/index

```hcl
module "bedrock_knowledge_base" {
  source      = "../../modules/bedrock-knowledge-base"
  environment = var.environment

  create_source_bucket       = false
  existing_source_bucket_arn = "arn:aws:s3:::my-existing-corporate-docs-bucket"

  create_vector_resources    = false
  existing_vector_bucket_arn = "arn:aws:s3vectors:ap-southeast-2:123456789012:bucket/shared-vectors"
  existing_vector_index_arn  = "arn:aws:s3vectors:ap-southeast-2:123456789012:bucket/shared-vectors/index/corporate-kb-index"
}
```

### Feeding the agent IAM roles module (Task 3.4)

```hcl
module "agent_iam_roles" {
  source      = "../../modules/agent-iam-roles"
  environment = var.environment

  knowledge_base_arn = module.bedrock_knowledge_base.knowledge_base_arn
}
```

### Top-k retrieval (Requirement 9.1)

This module does not itself enforce top-k retrieval — that is a parameter each agent supplies on
its own `Retrieve`/`RetrieveAndGenerate` call against `knowledge_base_id`. This module surfaces a
single documented default (`var.default_retrieval_top_k`, default `5`) via the
`default_retrieval_top_k` output so every agent's retrieval call configuration starts from the
same value:

```hcl
locals {
  kb_retrieval_top_k = module.bedrock_knowledge_base.default_retrieval_top_k
}
```

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; namespaces the KB, bucket, and vector resource names. | `string` | n/a (required) |
| `name_prefix` | Prefix for generated resource names. | `string` | `"daf-phase1"` |
| `kb_name` | Explicit KB name override. | `string` | `null` (derived) |
| `kb_description` | KB description. | `string` | Phase 1 default description |
| `create_source_bucket` | Whether to create the KB source S3 bucket. | `bool` | `true` |
| `source_bucket_name` | Explicit source bucket name override. | `string` | `null` (derived) |
| `existing_source_bucket_arn` | Existing bucket ARN to reuse. Required when `create_source_bucket = false`. | `string` | `null` |
| `source_bucket_inclusion_prefix` | Key prefix the S3 data source scopes ingestion to. | `string` | `""` (whole bucket) |
| `enable_bucket_versioning` | Whether the source bucket has versioning enabled. | `bool` | `true` |
| `kms_key_arn` | Optional KMS key for source bucket SSE-KMS encryption. | `string` | `null` (SSE-S3) |
| `force_destroy_source_bucket` | Whether the source bucket can be destroyed non-empty. | `bool` | `false` |
| `create_vector_resources` | Whether to create the S3 Vectors vector bucket/index. | `bool` | `true` |
| `vector_bucket_name` | Explicit vector bucket name override. | `string` | `null` (derived) |
| `vector_bucket_kms_key_arn` | Optional KMS key for vector bucket SSE-KMS encryption. | `string` | `null` (SSE-S3) |
| `vector_index_name` | Vector index name. | `string` | `"corporate-kb-index"` |
| `existing_vector_bucket_arn` | Existing vector bucket ARN to reuse. Required when `create_vector_resources = false`. | `string` | `null` |
| `existing_vector_index_arn` | Existing vector index ARN to reuse. Required when `create_vector_resources = false`. | `string` | `null` |
| `vector_distance_metric` | Similarity metric: `cosine` or `euclidean`. | `string` | `"cosine"` |
| `vector_data_type` | Vector data type (only `float32` supported by S3 Vectors today). | `string` | `"float32"` |
| `embedding_model_id` | Bedrock embedding model ID used to derive the default ARN. | `string` | `"amazon.titan-embed-text-v2:0"` |
| `embedding_model_arn` | Explicit embedding model ARN override. | `string` | `null` (derived) |
| `embedding_dimensions` | Embedding vector dimensionality; must match the vector index's `dimension`. | `number` | `1024` |
| `embedding_data_type` | `FLOAT32` or `BINARY`. | `string` | `"FLOAT32"` |
| `chunking_strategy` | `FIXED_SIZE`, `HIERARCHICAL`, `SEMANTIC`, or `NONE`. | `string` | `"FIXED_SIZE"` |
| `fixed_size_chunking_max_tokens` | Max tokens per chunk (FIXED_SIZE only). | `number` | `512` |
| `fixed_size_chunking_overlap_percentage` | Overlap % between chunks (FIXED_SIZE only). | `number` | `20` |
| `default_retrieval_top_k` | Documented default top-k for agent retrieval calls (Requirement 9.1). | `number` | `5` |
| `kb_role_name` | Explicit full KB service role name override. Must begin with `AmazonBedrockExecutionRoleForKnowledgeBase_`. | `string` | `null` (derived) |
| `kb_role_name_suffix` | Suffix appended to the required role-name prefix when `kb_role_name` is left null. Max 21 characters. | `string` | `null` (derived: `"<name_prefix>-<environment>"`) |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `knowledge_base_id` | ID of the Bedrock Knowledge Base. |
| `knowledge_base_arn` | ARN of the Bedrock Knowledge Base. **Feed into Task 3.4's `agent_iam_roles` module (`var.knowledge_base_arn`).** |
| `knowledge_base_name` | Name of the Bedrock Knowledge Base. |
| `knowledge_base_status` | `CREATING`/`ACTIVE`/`DELETING`/`UPDATING`/`FAILED`/`DELETE_UNSUCCESSFUL`/`UPDATE_UNSUCCESSFUL`. |
| `data_source_id` | ID of the KB's S3 data source. |
| `data_source_name` | Name of the KB's S3 data source. |
| `source_bucket_name` | Name of the KB source bucket. |
| `source_bucket_arn` | ARN of the KB source bucket. |
| `kb_service_role_arn` | ARN of the KB service role. |
| `kb_service_role_name` | Name of the KB service role. |
| `vector_bucket_name` | Name of the S3 Vectors vector bucket. |
| `vector_bucket_arn` | ARN of the S3 Vectors vector bucket. |
| `vector_index_name` | Name of the S3 Vectors vector index. |
| `vector_index_arn` | ARN of the S3 Vectors vector index. |
| `embedding_model_arn` | ARN of the Bedrock embedding model used by the KB. |
| `default_retrieval_top_k` | Documented default top-k for agent retrieval calls. |

## Requirements traceability

- Requirement 9.1: "WHEN an agent needs corporate guidance THEN it SHALL retrieve top-k chunks
  (not the whole KB) from the Bedrock Knowledge Base backed by S3 and the S3 Vectors vector
  store." — this module provisions that exact KB (S3 data source + S3 Vectors vector store) and
  surfaces a documented default top-k value; each agent's own `Retrieve`/`RetrieveAndGenerate`
  call (Task 13.4 Modernization Agent, Task 13.6 KB-vs-AWS-Docs conflict detection, and any other
  KB-consuming agent) is responsible for actually passing a top-k parameter on each call.
