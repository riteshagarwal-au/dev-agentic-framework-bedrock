output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base, for agents (Task 13.4 Modernization Agent, Task 13.6 KB-vs-AWS-Docs conflict detection) and Task 13.7's Bedrock Agent resources to associate against."
  value       = awscc_bedrock_knowledge_base.this.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base. Consumed by Task 3.4's agent-iam-roles module (var.knowledge_base_arn) to grant Security/Modernization/Portfolio Assessment agent roles read-only bedrock:Retrieve/RetrieveAndGenerate access."
  value       = awscc_bedrock_knowledge_base.this.knowledge_base_arn
}

output "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base."
  value       = local.kb_name
}

output "knowledge_base_status" {
  description = "Status of the Bedrock Knowledge Base (CREATING, ACTIVE, DELETING, UPDATING, FAILED, DELETE_UNSUCCESSFUL, UPDATE_UNSUCCESSFUL)."
  value       = awscc_bedrock_knowledge_base.this.status
}

output "data_source_id" {
  description = "ID of the Bedrock Knowledge Base's S3 data source, for downstream consumers (Task 13.4, Task 13.6) that need to trigger/monitor ingestion jobs."
  value       = awscc_bedrock_data_source.s3.data_source_id
}

output "data_source_name" {
  description = "Name of the Bedrock Knowledge Base's S3 data source."
  value       = awscc_bedrock_data_source.s3.name
}

output "source_bucket_name" {
  description = "Name of the S3 bucket holding the corporate KB's source documents."
  value       = var.create_source_bucket ? aws_s3_bucket.kb_source[0].id : null
}

output "source_bucket_arn" {
  description = "ARN of the S3 bucket holding the corporate KB's source documents (created by this module, or the existing bucket passed in via existing_source_bucket_arn)."
  value       = local.source_bucket_arn
}

output "kb_service_role_arn" {
  description = "ARN of the IAM role Bedrock assumes to operate this knowledge base, scoped to the source bucket, embedding model, and S3 Vectors vector bucket/index only."
  value       = aws_iam_role.kb_service_role.arn
}

output "kb_service_role_name" {
  description = "Name of the IAM role Bedrock assumes to operate this knowledge base."
  value       = aws_iam_role.kb_service_role.name
}

output "vector_bucket_name" {
  description = "Name of the S3 Vectors vector bucket backing this knowledge base."
  value       = local.vector_bucket_name
}

output "vector_bucket_arn" {
  description = "ARN of the S3 Vectors vector bucket backing this knowledge base (created by this module, or the existing bucket passed in via existing_vector_bucket_arn)."
  value       = local.vector_bucket_arn
}

output "vector_index_name" {
  description = "Name of the S3 Vectors vector index backing this knowledge base."
  value       = var.vector_index_name
}

output "vector_index_arn" {
  description = "ARN of the S3 Vectors vector index backing this knowledge base (created by this module, or the existing index passed in via existing_vector_index_arn)."
  value       = local.vector_index_arn
}

output "embedding_model_arn" {
  description = "ARN of the Bedrock embedding model the KB service role is permitted to invoke, and that the knowledge base is configured to use."
  value       = local.embedding_model_arn
}

output "default_retrieval_top_k" {
  description = "Default top-k value agents should use for Retrieve/RetrieveAndGenerate calls against this knowledge base, per Requirement 9.1."
  value       = var.default_retrieval_top_k
}
