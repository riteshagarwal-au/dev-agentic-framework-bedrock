# Phase 1 is single-account/single-region, so `dev` is the only environment defined for now.
# Additional per-environment .tfvars files (e.g. staging.tfvars, prod.tfvars) are added here if/when
# Phase 1 scope expands to multiple environments.

aws_region  = "ap-southeast-2"
environment = "dev"
project_tag = "daf-phase1"
