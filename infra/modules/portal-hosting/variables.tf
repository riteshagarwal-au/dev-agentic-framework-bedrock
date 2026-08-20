variable "environment" {
  description = "Environment name (e.g. dev). Used for resource naming."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to resource names created by this module."
  type        = string
}
