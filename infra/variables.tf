variable "aws_region" {
  description = "AWS region for all DAF Phase 1 resources (single-region in Phase 1)."
  type        = string
  default     = "ap-southeast-2"
}

variable "environment" {
  description = "Environment name for this root module invocation (e.g. dev). Phase 1 is single-account/single-region, so only one environment is expected initially."
  type        = string
}

variable "project_tag" {
  description = "Value applied to the Project tag on every resource created by this root module."
  type        = string
  default     = "daf-phase1"
}
