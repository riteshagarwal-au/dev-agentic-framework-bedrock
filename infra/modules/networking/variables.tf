variable "environment" {
  description = <<-EOT
    Environment or deploy-target name this networking module belongs to (e.g. "dev"). Used to
    namespace resource names/tags so multiple environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to every resource name/tag created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zone_count" {
  description = <<-EOT
    Number of Availability Zones to spread public/private subnets across. Phase 1 is
    single-region but still wants basic within-region availability, so this defaults to 2.
    Must be >= 2 and <= the number of AZs available in the target region.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2
    error_message = "availability_zone_count must be at least 2 for basic availability."
  }
}

variable "public_subnet_newbits" {
  description = <<-EOT
    Number of additional bits used to carve public subnets out of var.vpc_cidr via cidrsubnet().
    With the default /16 VPC and newbits = 8, each public subnet is a /24.
  EOT
  type        = number
  default     = 8
}

variable "private_subnet_newbits" {
  description = <<-EOT
    Number of additional bits used to carve private subnets out of var.vpc_cidr via cidrsubnet().
    Private subnets are numbered after all public subnets in the same address space, so with the
    default /16 VPC and newbits = 8, each private subnet is also a /24.
  EOT
  type        = number
  default     = 8
}

variable "single_nat_gateway" {
  description = <<-EOT
    Whether to create a single shared NAT Gateway (cost-optimized, one AZ of egress-path
    exposure) instead of one NAT Gateway per AZ (higher availability, higher cost). Phase 1
    defaults to a single NAT Gateway since it is not a hard security/availability boundary for
    this phase (see module README "Phase 1 scope boundary").
  EOT
  type        = bool
  default     = true
}

variable "enable_dns_hostnames" {
  description = "Whether to enable DNS hostnames in the VPC (required by many AWS-managed services)."
  type        = bool
  default     = true
}

variable "enable_dns_support" {
  description = "Whether to enable DNS resolution in the VPC."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
