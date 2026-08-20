variable "environment" {
  description = <<-EOT
    Environment or deploy-target name this state backend belongs to (e.g. "dev", "staging",
    "prod", or a per-target name). Each distinct value should get its own module instance/bucket
    so environments/targets never share (and can never collide on) the same remote state bucket.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "bucket_name_prefix" {
  description = <<-EOT
    Prefix used to build the state bucket name: "<bucket_name_prefix>-<environment>-<account_id>".
    The AWS account ID is appended automatically to keep the (globally unique) bucket name from
    colliding with the same environment name used in a different account.
  EOT
  type        = string
  default     = "daf-tfstate"
}

variable "create_kms_key" {
  description = "Whether this module creates a dedicated KMS key for state encryption. Set to false and supply kms_key_arn to reuse an existing key instead."
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of an existing KMS key to use for bucket encryption. Required (and only used) when create_kms_key = false."
  type        = string
  default     = null

  validation {
    condition     = var.create_kms_key || var.kms_key_arn != null
    error_message = "kms_key_arn must be set when create_kms_key = false."
  }
}

variable "kms_key_deletion_window_in_days" {
  description = "Deletion window (in days) for the KMS key created by this module. Ignored when create_kms_key = false."
  type        = number
  default     = 30
}

variable "force_destroy" {
  description = <<-EOT
    Whether the state bucket can be destroyed even if it still contains objects. This should stay
    false everywhere except short-lived scratch/test environments — a Terraform state bucket
    should never be deleted out from under a live backend.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
