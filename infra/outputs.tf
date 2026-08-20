# No resources are created directly by the root module yet (Task 1.3 is scaffolding only).
# Outputs will be added here as submodules under infra/modules/ are wired into the root module
# in later tasks (2.x, 3.x, 5.1, 14.3).

output "portal_url" {
  description = "DAF Portal URL (CloudFront distribution serving the S3-hosted React SPA)."
  value       = module.portal_hosting.portal_url
}

output "portal_api_endpoint" {
  description = "Base invoke URL of the Portal API HTTP API (API Gateway v2)."
  value       = module.portal_api.api_endpoint
}

output "artifact_bucket_name" {
  description = "S3 bucket holding real generated migration artifacts (inventory, blueprint, Terraform plan)."
  value       = module.portal_api.artifact_bucket_name
}

output "cognito_user_pool_domain" {
  description = "Cognito Hosted UI domain for the Portal user pool."
  value       = module.cognito_auth.user_pool_domain
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID for the Portal SPA (public client, no secret)."
  value       = module.cognito_auth.user_pool_client_id
}
