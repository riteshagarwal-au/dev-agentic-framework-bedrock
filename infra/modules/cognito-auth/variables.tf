variable "environment" {
  description = "Environment name (e.g. dev). Used for resource naming."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to resource names created by this module."
  type        = string
}

variable "callback_urls" {
  description = "Allowed OAuth callback URLs for the portal SPA (e.g. the CloudFront URL)."
  type        = list(string)
}

variable "logout_urls" {
  description = "Allowed OAuth logout URLs for the portal SPA."
  type        = list(string)
}
