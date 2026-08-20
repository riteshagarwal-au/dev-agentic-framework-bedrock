variable "environment" {
  description = "Environment name (e.g. dev). Used for resource naming."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to resource names created by this module."
  type        = string
}

variable "backend_src_dir" {
  description = "Path to the backend/src directory containing the daf Python package, packaged into each Lambda's deployment zip."
  type        = string
}

variable "backend_site_packages_dir" {
  description = <<-EOT
    Path to a directory containing this Lambda's third-party dependencies (pydantic, boto3 is
    already present in the Lambda runtime and excluded), pre-installed for the Lambda's target
    architecture/runtime (e.g. via `pip install -r requirements.txt -t <dir> --python-version
    3.12 --platform manylinux2014_x86_64 --only-binary=:all:`). Merged into the same deployment
    zip as backend_src_dir.
  EOT
  type        = string
}

variable "run_state_table_name" {
  type = string
}

variable "run_state_table_arn" {
  type = string
}

variable "run_counters_table_name" {
  type = string
}

variable "run_counters_table_arn" {
  type = string
}

variable "gate_ticket_table_name" {
  type = string
}

variable "gate_ticket_table_arn" {
  type = string
}

variable "hitl_state_machine_arn" {
  description = "ARN of the HITL gate Step Functions state machine, used for send_task_success/send_task_failure on gate decisions."
  type        = string
}

variable "cognito_user_pool_client_id" {
  type = string
}

variable "cognito_issuer_url" {
  type = string
}

variable "cors_allowed_origins" {
  description = "Allowed CORS origins for the HTTP API (the portal's CloudFront URL)."
  type        = list(string)
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 15
}

variable "lambda_memory_mb" {
  type    = number
  default = 256
}
