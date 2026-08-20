terraform {
  # Matches the root module's floor (see ../../versions.tf) so this module can be validated
  # standalone.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    # NEW provider dependency relative to most other modules under infra/modules/ (mirrors the
    # precedent set by Task 3.3's bedrock-agentcore-memory module). The pinned `hashicorp/aws`
    # provider (~> 5.0, validated against 5.100.0 per the root .terraform.lock.hcl) has NO
    # aws_s3vectors_* resources at all (added to `hashicorp/aws` only in v6.24.0), and its
    # aws_bedrockagent_knowledge_base's storage_configuration only supports OpenSearch
    # Serverless/Pinecone/RDS/Redis Enterprise Cloud in that version line — no S3 Vectors option
    # (added to `hashicorp/aws` only in v6.27.0). Rather than fabricate a v5-era resource that
    # doesn't exist, or substitute an out-of-scope backend (OpenSearch Serverless), this module
    # uses the AWS Cloud Control provider's awscc_s3vectors_vector_bucket, awscc_s3vectors_index,
    # awscc_bedrock_knowledge_base, and awscc_bedrock_data_source resources instead, which have
    # real, currently-shipping support for the S3 Vectors backend. See this module's README
    # "Provider version note" for full detail.
    awscc = {
      source  = "hashicorp/awscc"
      version = "~> 1.59"
    }
  }
}
