variable "environment" {
  description = "Environment name (e.g. dev). Used for resource naming/tagging."
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to resource names created by this module."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID the ECS service's tasks and security group are created in (networking module output vpc_id)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs the ECS Fargate tasks run in (networking module output private_subnet_ids)."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) > 0
    error_message = "private_subnet_ids must contain at least one subnet."
  }
}

variable "container_port" {
  description = "Port the target app's container listens on."
  type        = number
  default     = 8080
}

variable "task_cpu" {
  description = "Fargate task-level vCPU units (Fargate CPU/memory combinations apply)."
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task-level memory (MiB)."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of running tasks for the target app's ECS service."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
