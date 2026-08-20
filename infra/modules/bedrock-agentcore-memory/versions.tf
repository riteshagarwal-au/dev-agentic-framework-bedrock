terraform {
  # Matches the root module's floor (see ../../versions.tf) so this module can be validated
  # standalone.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    # NOTE: this is a NEW provider dependency relative to every other module under
    # infra/modules/ (all of which only need `hashicorp/aws`). The pinned `hashicorp/aws`
    # provider (~> 5.0, validated against 5.100.0 per the root .terraform.lock.hcl) has NO
    # `aws_bedrockagentcore_*` resources at all in that version line — Bedrock AgentCore Memory
    # support only landed in `hashicorp/aws` v6.18.0 (October 2025, well past this repo's `~> 5.0`
    # ceiling) as `aws_bedrockagentcore_memory` / `aws_bedrockagentcore_memory_strategy`. Rather
    # than fabricate a v5-era resource that doesn't exist, this module uses the AWS Cloud Control
    # provider's `awscc_bedrockagentcore_memory` resource instead, which has provided real
    # AgentCore Memory support since v1.59.0 (October 2025) and is still actively maintained.
    # See this module's README "Provider version note" for full detail and the tradeoffs of this
    # choice, and infra/README.md / infra/providers.tf for the root-level wiring this new
    # provider dependency requires once this module is instantiated.
    awscc = {
      source  = "hashicorp/awscc"
      version = "~> 1.59"
    }
  }
}
