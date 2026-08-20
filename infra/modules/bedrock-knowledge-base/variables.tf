variable "environment" {
  description = <<-EOT
    Environment or deploy-target name this knowledge base belongs to (e.g. "dev"). Used to
    namespace the KB name, source bucket name, vector bucket/index names, and tags so multiple
    environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to generated resource names and tags created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

variable "kb_name" {
  description = <<-EOT
    Name of the Bedrock Knowledge Base. Defaults to "<name_prefix>-corporate-kb-<environment>"
    when left null. Must match Bedrock's knowledge base name pattern (letters, digits,
    hyphens, underscores).
  EOT
  type        = string
  default     = null
}

variable "kb_description" {
  description = "Description of the Bedrock Knowledge Base."
  type        = string
  default     = "DAF Phase 1 corporate knowledge base (authoritative migration/architecture guidance), backed by S3 + S3 Vectors per Requirement 9.1."
}

# ---------------------------------------------------------------------------
# S3 data source bucket (create-or-reuse, mirrors state-backend's
# create_kms_key pattern).
# ---------------------------------------------------------------------------

variable "create_source_bucket" {
  description = <<-EOT
    Whether this module creates the S3 bucket holding the corporate KB's source documents. Set to
    false and supply existing_source_bucket_arn to reuse a bucket created elsewhere instead.
  EOT
  type        = bool
  default     = true
}

variable "source_bucket_name" {
  description = <<-EOT
    Explicit name for the KB source bucket. Defaults to
    "<name_prefix>-kb-source-<environment>-<account_id>" when left null. Ignored when
    create_source_bucket = false.
  EOT
  type        = string
  default     = null
}

variable "existing_source_bucket_arn" {
  description = "ARN of an existing S3 bucket to use as the KB source bucket. Required (and only used) when create_source_bucket = false."
  type        = string
  default     = null

  validation {
    condition     = var.create_source_bucket || var.existing_source_bucket_arn != null
    error_message = "existing_source_bucket_arn must be set when create_source_bucket = false."
  }
}

variable "source_bucket_inclusion_prefix" {
  description = <<-EOT
    Optional key prefix within the source bucket that the S3 data source scopes ingestion to
    (e.g. "corporate-kb/"). Left empty (the default) to ingest the whole bucket.
  EOT
  type        = string
  default     = ""
}

variable "enable_bucket_versioning" {
  description = "Whether the KB source bucket has versioning enabled."
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = <<-EOT
    Optional KMS key ARN used to encrypt the KB source bucket at rest (SSE-KMS). Leave null to use
    SSE-S3 (AES256) default encryption instead. This module does not create a KMS key itself —
    pass an existing key ARN (e.g. from a shared key or another module's output) if SSE-KMS is
    required.
  EOT
  type        = string
  default     = null
}

variable "force_destroy_source_bucket" {
  description = "Whether the KB source bucket can be destroyed even if it still contains objects. Keep false outside scratch/test environments."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# S3 Vectors backend (Phase 1 KB vector store per design.md §6.1.1 / Requirement 9.1).
# create-or-reuse, mirroring the source bucket's pattern: create_vector_resources = false +
# existing_vector_bucket_arn/existing_vector_index_arn reuses a vector bucket/index created
# elsewhere instead.
# ---------------------------------------------------------------------------

variable "create_vector_resources" {
  description = <<-EOT
    Whether this module creates the S3 Vectors vector bucket and vector index that back this
    knowledge base. Set to false and supply existing_vector_bucket_arn and
    existing_vector_index_arn to reuse a vector bucket/index created elsewhere instead.
  EOT
  type        = bool
  default     = true
}

variable "vector_bucket_name" {
  description = <<-EOT
    Name of the S3 Vectors vector bucket. Defaults to "<name_prefix>-kb-vectors-<environment>"
    when left null. Must be lowercase letters, numbers, and hyphens only (3-63 characters) — S3
    Vectors bucket names do not allow uppercase characters or underscores, unlike most other DAF
    Phase 1 resource names. Ignored when create_vector_resources = false.
  EOT
  type        = string
  default     = null
}

variable "vector_bucket_kms_key_arn" {
  description = <<-EOT
    Optional KMS key ARN used to encrypt the S3 Vectors vector bucket at rest (SSE-KMS). Leave
    null to use the S3 Vectors default (SSE-S3, AES256). Ignored when create_vector_resources =
    false.
  EOT
  type        = string
  default     = null
}

variable "vector_index_name" {
  description = <<-EOT
    Name of the S3 Vectors vector index within the vector bucket that stores this knowledge
    base's embeddings. Must be lowercase letters, numbers, hyphens, and dots only (3-63
    characters).
  EOT
  type        = string
  default     = "corporate-kb-index"

  validation {
    condition     = length(var.vector_index_name) >= 3 && length(var.vector_index_name) <= 63
    error_message = "vector_index_name must be between 3 and 63 characters."
  }
}

variable "existing_vector_bucket_arn" {
  description = "ARN of an existing S3 Vectors vector bucket to use. Required (and only used) when create_vector_resources = false."
  type        = string
  default     = null

  validation {
    condition     = var.create_vector_resources || var.existing_vector_bucket_arn != null
    error_message = "existing_vector_bucket_arn must be set when create_vector_resources = false."
  }
}

variable "existing_vector_index_arn" {
  description = "ARN of an existing S3 Vectors vector index to use. Required (and only used) when create_vector_resources = false."
  type        = string
  default     = null

  validation {
    condition     = var.create_vector_resources || var.existing_vector_index_arn != null
    error_message = "existing_vector_index_arn must be set when create_vector_resources = false."
  }
}

variable "vector_distance_metric" {
  description = "Distance metric used for similarity search over the vector index. One of cosine or euclidean."
  type        = string
  default     = "cosine"

  validation {
    condition     = contains(["cosine", "euclidean"], var.vector_distance_metric)
    error_message = "vector_distance_metric must be one of cosine or euclidean."
  }
}

variable "vector_data_type" {
  description = "Data type of the vectors stored in the S3 Vectors index. Currently only float32 is supported by the service."
  type        = string
  default     = "float32"

  validation {
    condition     = var.vector_data_type == "float32"
    error_message = "vector_data_type must be float32 (the only value currently supported by S3 Vectors)."
  }
}

# ---------------------------------------------------------------------------
# Embedding model (used both for the vector_knowledge_base_configuration and to scope the KB
# service role's bedrock:InvokeModel permission).
# ---------------------------------------------------------------------------

variable "embedding_model_id" {
  description = <<-EOT
    Bedrock foundation model ID used to derive the default embedding_model_arn when
    embedding_model_arn is left null. Defaults to Titan Text Embeddings V2.
  EOT
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_model_arn" {
  description = <<-EOT
    Explicit ARN of the Bedrock embedding model used by this knowledge base. Defaults to
    "arn:<partition>:bedrock:<region>::foundation-model/<embedding_model_id>" when left null.
  EOT
  type        = string
  default     = null
}

variable "embedding_dimensions" {
  description = <<-EOT
    Embedding vector dimensionality produced by the embedding model (e.g. 1024 for Titan Text
    Embeddings V2). Must match the vector index's dimension exactly — a mismatch causes
    ingestion failures, not a Terraform-time error, since both values are user-supplied.
  EOT
  type        = number
  default     = 1024

  validation {
    condition     = var.embedding_dimensions >= 1 && var.embedding_dimensions <= 4096
    error_message = "embedding_dimensions must be between 1 and 4096 (S3 Vectors index limit)."
  }
}

variable "embedding_data_type" {
  description = "Data type for the vectors produced by the embedding model. One of FLOAT32 or BINARY."
  type        = string
  default     = "FLOAT32"

  validation {
    condition     = contains(["FLOAT32", "BINARY"], var.embedding_data_type)
    error_message = "embedding_data_type must be one of FLOAT32 or BINARY."
  }
}

# ---------------------------------------------------------------------------
# Chunking strategy (Phase 1 defaults) for the S3 data source's ingestion configuration.
# ---------------------------------------------------------------------------

variable "chunking_strategy" {
  description = "Chunking strategy for KB document ingestion. One of FIXED_SIZE, HIERARCHICAL, SEMANTIC, or NONE. Phase 1 defaults to FIXED_SIZE."
  type        = string
  default     = "FIXED_SIZE"

  validation {
    condition     = contains(["FIXED_SIZE", "HIERARCHICAL", "SEMANTIC", "NONE"], var.chunking_strategy)
    error_message = "chunking_strategy must be one of FIXED_SIZE, HIERARCHICAL, SEMANTIC, or NONE."
  }
}

variable "fixed_size_chunking_max_tokens" {
  description = "Maximum tokens per chunk when chunking_strategy = FIXED_SIZE."
  type        = number
  default     = 512

  validation {
    condition     = var.fixed_size_chunking_max_tokens >= 1
    error_message = "fixed_size_chunking_max_tokens must be at least 1."
  }
}

variable "fixed_size_chunking_overlap_percentage" {
  description = "Overlap percentage (1-99) between adjacent chunks when chunking_strategy = FIXED_SIZE."
  type        = number
  default     = 20

  validation {
    condition     = var.fixed_size_chunking_overlap_percentage >= 1 && var.fixed_size_chunking_overlap_percentage <= 99
    error_message = "fixed_size_chunking_overlap_percentage must be between 1 and 99."
  }
}

# ---------------------------------------------------------------------------
# Retrieval expectation (Requirement 9.1: "retrieve top-k chunks, not the whole KB"). This module
# does not enforce top-k itself (that's a parameter on each agent's Retrieve/RetrieveAndGenerate
# call) — this default is surfaced via output so every agent's retrieval call has a single
# documented default to start from.
# ---------------------------------------------------------------------------

variable "default_retrieval_top_k" {
  description = "Default number of top-k chunks agents should request from Retrieve/RetrieveAndGenerate calls against this knowledge base, per Requirement 9.1."
  type        = number
  default     = 5

  validation {
    condition     = var.default_retrieval_top_k >= 1
    error_message = "default_retrieval_top_k must be at least 1."
  }
}

# ---------------------------------------------------------------------------
# KB service role naming. Bedrock enforces that a knowledge base's role ARN begins with the
# literal prefix "AmazonBedrockExecutionRoleForKnowledgeBase_" (the same convention enforced for
# Bedrock Agents' "AmazonBedrockExecutionRoleForAgents_" prefix). IAM role names are capped at 64
# characters, and the prefix alone is 43 characters, leaving only 21 characters for the suffix —
# too tight to reuse the full "<name_prefix>-corporate-kb-<environment>" kb_name. Default to a
# short "<name_prefix>-<environment>" suffix instead.
# ---------------------------------------------------------------------------

variable "kb_role_name" {
  description = <<-EOT
    Explicit full name for the KB service role, overriding the derived
    "AmazonBedrockExecutionRoleForKnowledgeBase_<kb_role_name_suffix>" default. Must begin with
    "AmazonBedrockExecutionRoleForKnowledgeBase_" (enforced by the Bedrock API) and be at most 64
    characters. Leave null (the default) to use the derived name.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.kb_role_name == null || can(regex("^AmazonBedrockExecutionRoleForKnowledgeBase_", var.kb_role_name))
    error_message = "kb_role_name, if set, must begin with \"AmazonBedrockExecutionRoleForKnowledgeBase_\"."
  }

  validation {
    condition     = var.kb_role_name == null || length(var.kb_role_name) <= 64
    error_message = "kb_role_name, if set, must be at most 64 characters (IAM role name limit)."
  }
}

variable "kb_role_name_suffix" {
  description = <<-EOT
    Suffix appended to the "AmazonBedrockExecutionRoleForKnowledgeBase_" prefix to derive the KB
    service role name when kb_role_name is left null. Defaults to "<name_prefix>-<environment>".
    Must be at most 21 characters (64 character IAM role name limit minus the 43-character
    required prefix).
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.kb_role_name_suffix == null || length(var.kb_role_name_suffix) <= 21
    error_message = "kb_role_name_suffix, if set, must be at most 21 characters (64 character IAM role name limit minus the 43-character required prefix)."
  }
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
