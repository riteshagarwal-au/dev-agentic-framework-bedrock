data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  kb_name = coalesce(var.kb_name, "${var.name_prefix}-corporate-kb-${var.environment}")

  kb_role_name_suffix = coalesce(var.kb_role_name_suffix, "${var.name_prefix}-${var.environment}")
  kb_role_name        = coalesce(var.kb_role_name, "AmazonBedrockExecutionRoleForKnowledgeBase_${local.kb_role_name_suffix}")

  source_bucket_name = coalesce(
    var.source_bucket_name,
    "${var.name_prefix}-kb-source-${var.environment}-${data.aws_caller_identity.current.account_id}"
  )
  source_bucket_arn = var.create_source_bucket ? aws_s3_bucket.kb_source[0].arn : var.existing_source_bucket_arn

  vector_bucket_name = coalesce(var.vector_bucket_name, "${var.name_prefix}-kb-vectors-${var.environment}")

  vector_bucket_arn = var.create_vector_resources ? awscc_s3vectors_vector_bucket.this[0].vector_bucket_arn : var.existing_vector_bucket_arn
  vector_index_arn  = var.create_vector_resources ? awscc_s3vectors_index.this[0].index_arn : var.existing_vector_index_arn

  embedding_model_arn = coalesce(
    var.embedding_model_arn,
    "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.name}::foundation-model/${var.embedding_model_id}"
  )

  tags = merge(var.tags, {
    Name        = local.kb_name
    Environment = var.environment
    Purpose     = "bedrock-corporate-knowledge-base"
  })
}

# ---------------------------------------------------------------------------
# S3 bucket for the corporate KB's source documents (the Bedrock KB's S3 data source, per
# Requirement 9.1 / design.md §6.1.1 "Bedrock KB on S3 + S3 Vectors"). create-or-reuse,
# mirroring state-backend's create_kms_key pattern: create_source_bucket = false +
# existing_source_bucket_arn reuses a bucket created elsewhere.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "kb_source" {
  count = var.create_source_bucket ? 1 : 0

  bucket        = local.source_bucket_name
  force_destroy = var.force_destroy_source_bucket

  tags = merge(local.tags, {
    Name    = local.source_bucket_name
    Purpose = "bedrock-kb-source-documents"
  })
}

resource "aws_s3_bucket_versioning" "kb_source" {
  count = var.create_source_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_source[0].id

  versioning_configuration {
    status = var.enable_bucket_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "kb_source" {
  count = var.create_source_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_source[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_public_access_block" "kb_source" {
  count = var.create_source_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_source[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "kb_source" {
  count = var.create_source_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_source[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# ---------------------------------------------------------------------------
# S3 Vectors vector bucket + index — the Phase 1 KB vector store per design.md §6.1.1 and
# Requirement 9.1. Provisioned via the AWS Cloud Control provider's awscc_s3vectors_vector_bucket
# / awscc_s3vectors_index resources, NOT hashicorp/aws's (nonexistent, in this provider version)
# aws_s3vectors_* resources — see this module's README "Provider version note".
# create-or-reuse: create_vector_resources = false + existing_vector_bucket_arn /
# existing_vector_index_arn reuses vector resources created elsewhere.
# ---------------------------------------------------------------------------

resource "awscc_s3vectors_vector_bucket" "this" {
  count = var.create_vector_resources ? 1 : 0

  vector_bucket_name = local.vector_bucket_name

  encryption_configuration = {
    sse_type    = var.vector_bucket_kms_key_arn != null ? "aws:kms" : "AES256"
    kms_key_arn = var.vector_bucket_kms_key_arn
  }

  tags = [
    for k, v in local.tags : { key = k, value = v }
  ]
}

resource "awscc_s3vectors_index" "this" {
  count = var.create_vector_resources ? 1 : 0

  vector_bucket_name = awscc_s3vectors_vector_bucket.this[0].vector_bucket_name
  index_name         = var.vector_index_name
  data_type          = var.vector_data_type
  dimension          = var.embedding_dimensions
  distance_metric    = var.vector_distance_metric

  tags = [
    for k, v in local.tags : { key = k, value = v }
  ]
}

# ---------------------------------------------------------------------------
# Knowledge Base service role (bedrock.amazonaws.com principal), scoped to:
#   - this KB's S3 source bucket only (read + list)
#   - this KB's Bedrock embedding model only (InvokeModel)
#   - this KB's S3 Vectors vector bucket/index only (read/write vectors)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "kb_trust" {
  statement {
    sid     = "BedrockKnowledgeBaseAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "kb_service_role" {
  name               = local.kb_role_name
  assume_role_policy = data.aws_iam_policy_document.kb_trust.json
  description        = "Bedrock Knowledge Base service role for ${local.kb_name}, scoped to its S3 source bucket and S3 Vectors backend only (Requirement 9.1)."

  tags = merge(local.tags, {
    Name = local.kb_role_name
  })
}

data "aws_iam_policy_document" "kb_permissions" {
  statement {
    sid    = "S3SourceBucketList"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
    ]
    resources = [local.source_bucket_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid    = "S3SourceObjectRead"
    effect = "Allow"
    actions = [
      "s3:GetObject",
    ]
    resources = [
      var.source_bucket_inclusion_prefix != "" ? "${local.source_bucket_arn}/${var.source_bucket_inclusion_prefix}*" : "${local.source_bucket_arn}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid       = "InvokeEmbeddingModel"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embedding_model_arn]
  }

  # S3 Vectors permissions, per AWS's "Permissions to access your vector store in Amazon S3
  # Vectors" (kb-permissions.html) plus the read/write vector data-plane actions the KB
  # ingestion/retrieval path needs.
  statement {
    sid    = "S3VectorsBucketAccess"
    effect = "Allow"
    actions = [
      "s3vectors:GetVectorBucket",
      "s3vectors:GetIndex",
      "s3vectors:ListIndexes",
    ]
    resources = [
      local.vector_bucket_arn,
      local.vector_index_arn,
    ]
  }

  statement {
    sid    = "S3VectorsDataAccess"
    effect = "Allow"
    actions = [
      "s3vectors:PutVectors",
      "s3vectors:GetVectors",
      "s3vectors:ListVectors",
      "s3vectors:QueryVectors",
      "s3vectors:DeleteVectors",
    ]
    resources = [local.vector_index_arn]
  }

  dynamic "statement" {
    for_each = var.kms_key_arn != null ? [1] : []
    content {
      sid    = "KmsDecryptSourceBucket"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
      ]
      resources = [var.kms_key_arn]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["s3.${data.aws_region.current.name}.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_role_policy" "kb_permissions" {
  name   = "${local.kb_name}-permissions"
  role   = aws_iam_role.kb_service_role.id
  policy = data.aws_iam_policy_document.kb_permissions.json
}

# ---------------------------------------------------------------------------
# Bedrock Knowledge Base, storage type S3_VECTORS, per Requirement 9.1 / design.md §6.1.1.
#
# Provisioned via the AWS Cloud Control provider's awscc_bedrock_knowledge_base resource, NOT
# hashicorp/aws's aws_bedrockagent_knowledge_base — see this module's README "Provider version
# note": the repo's pinned hashicorp/aws (~> 5.0, validated at 5.100.0) only supports
# OpenSearch Serverless, Pinecone, RDS (Aurora), and Redis Enterprise Cloud as
# storage_configuration.type in that version line; S3 Vectors support landed in hashicorp/aws
# only in v6.27.0. awscc_bedrock_knowledge_base's storage_configuration.s3_vectors_configuration
# is a real, currently-shipping resource that supports S3 Vectors today.
# ---------------------------------------------------------------------------

resource "awscc_bedrock_knowledge_base" "this" {
  name        = local.kb_name
  description = var.kb_description
  role_arn    = aws_iam_role.kb_service_role.arn

  knowledge_base_configuration = {
    type = "VECTOR"

    vector_knowledge_base_configuration = {
      embedding_model_arn = local.embedding_model_arn

      embedding_model_configuration = {
        bedrock_embedding_model_configuration = {
          dimensions          = var.embedding_dimensions
          embedding_data_type = var.embedding_data_type
        }
      }
    }
  }

  storage_configuration = {
    type = "S3_VECTORS"

    s3_vectors_configuration = {
      vector_bucket_arn = local.vector_bucket_arn
      index_arn         = local.vector_index_arn
      index_name        = var.vector_index_name
    }
  }

  tags = local.tags

  depends_on = [aws_iam_role_policy.kb_permissions]
}

# ---------------------------------------------------------------------------
# S3 data source for the Knowledge Base, pointing at the KB source bucket, per Requirement 9.1
# ("Bedrock Knowledge Base backed by S3 ..."). Provisioned via the AWS Cloud Control provider's
# awscc_bedrock_data_source resource for the same reason the KB itself is (see README) — the two
# resources' schemas need to compose (data_source_configuration.type = "S3" is unaffected by the
# provider gap, but keeping both resources on the same provider avoids cross-provider ID/state
# plumbing between hashicorp/aws and hashicorp/awscc for a single logical KB).
# ---------------------------------------------------------------------------

resource "awscc_bedrock_data_source" "s3" {
  knowledge_base_id = awscc_bedrock_knowledge_base.this.knowledge_base_id
  name              = "${local.kb_name}-s3-source"
  description       = "S3 data source for ${local.kb_name}, per Requirement 9.1."

  data_source_configuration = {
    type = "S3"

    s3_configuration = {
      bucket_arn              = local.source_bucket_arn
      inclusion_prefixes      = var.source_bucket_inclusion_prefix != "" ? [var.source_bucket_inclusion_prefix] : null
      bucket_owner_account_id = data.aws_caller_identity.current.account_id
    }
  }

  vector_ingestion_configuration = {
    chunking_configuration = {
      chunking_strategy = var.chunking_strategy

      fixed_size_chunking_configuration = var.chunking_strategy == "FIXED_SIZE" ? {
        max_tokens         = var.fixed_size_chunking_max_tokens
        overlap_percentage = var.fixed_size_chunking_overlap_percentage
      } : null
    }
  }
}
