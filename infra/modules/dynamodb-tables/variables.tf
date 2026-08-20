variable "environment" {
  description = <<-EOT
    Environment or deploy-target name these tables belong to (e.g. "dev"). Used to namespace
    table names/tags so multiple environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to every table name created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

# ---------------------------------------------------------------------------
# Encryption (create-or-reuse KMS key, matching modules/state-backend's pattern)
# ---------------------------------------------------------------------------

variable "create_kms_key" {
  description = <<-EOT
    Whether this module creates a dedicated KMS key for table encryption. Set to false and supply
    kms_key_arn to reuse an existing key instead (e.g. a key already created by another module).
  EOT
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of an existing KMS key to use for table encryption. Required (and only used) when create_kms_key = false."
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

# ---------------------------------------------------------------------------
# GSI projection
# ---------------------------------------------------------------------------

variable "gsi_projection_type" {
  description = <<-EOT
    Projection type used by the runId GSIs on the GateTicket and DeadLetterRecord tables
    (`getPendingGates` (Task 9.3) and DeadLetterRecord list-by-run (Task 5.5) both need the full
    item, not just keys, so ALL is the simplest correct choice at Phase 1 scale). Override to
    "KEYS_ONLY" or "INCLUDE" if a future phase needs to trade GSI storage/throughput cost for a
    narrower projection.
  EOT
  type        = string
  default     = "ALL"

  validation {
    condition     = contains(["ALL", "KEYS_ONLY", "INCLUDE"], var.gsi_projection_type)
    error_message = "gsi_projection_type must be one of ALL, KEYS_ONLY, INCLUDE."
  }
}

variable "point_in_time_recovery_enabled" {
  description = "Whether point-in-time recovery is enabled on all 4 tables created by this module."
  type        = bool
  default     = true
}

variable "deletion_protection_enabled" {
  description = <<-EOT
    Whether DynamoDB deletion protection is enabled on all 4 tables. Defaults to false for Phase 1
    (dev/test iteration); set true for any environment where accidental `terraform destroy` of run
    state would be costly.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
