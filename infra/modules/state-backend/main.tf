data "aws_caller_identity" "current" {}

locals {
  bucket_name = "${var.bucket_name_prefix}-${var.environment}-${data.aws_caller_identity.current.account_id}"
  kms_key_arn = var.create_kms_key ? aws_kms_key.state[0].arn : var.kms_key_arn
}

# ---------------------------------------------------------------------------
# KMS key for Terraform state encryption (optional — a caller can instead
# pass an existing key via kms_key_arn / create_kms_key = false).
# ---------------------------------------------------------------------------

resource "aws_kms_key" "state" {
  count = var.create_kms_key ? 1 : 0

  description             = "KMS key for DAF Terraform state bucket (${var.environment})"
  deletion_window_in_days = var.kms_key_deletion_window_in_days
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name        = "${local.bucket_name}-kms"
    Environment = var.environment
  })
}

resource "aws_kms_alias" "state" {
  count = var.create_kms_key ? 1 : 0

  name          = "alias/${local.bucket_name}"
  target_key_id = aws_kms_key.state[0].key_id
}

# ---------------------------------------------------------------------------
# S3 bucket for Terraform remote state.
#
# NOTE on locking: Terraform's S3 backend supports native state locking via
# the `use_lockfile = true` backend-config setting (Terraform >= 1.11), which
# writes a `.tflock` companion object alongside the state object using S3's
# conditional-write (If-None-Match) support — no DynamoDB lock table needed.
# `use_lockfile` is a *backend configuration* setting used by consumers of
# this bucket (in their `backend "s3" { ... }` block), not a resource
# attribute on the bucket itself, so there is no corresponding resource
# argument here. See this module's README for the consumer-side example.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy

  tags = merge(var.tags, {
    Name        = local.bucket_name
    Environment = var.environment
    Purpose     = "terraform-remote-state"
  })
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = local.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Enforce TLS-only access and reject any unencrypted (non-KMS) PutObject.
data "aws_iam_policy_document" "state_bucket_policy" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyUnencryptedObjectUploads"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_bucket_policy.json
}
