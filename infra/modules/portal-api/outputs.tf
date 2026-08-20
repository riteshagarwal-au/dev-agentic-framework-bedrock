output "api_endpoint" {
  description = "Base invoke URL of the portal HTTP API."
  value       = aws_apigatewayv2_api.portal.api_endpoint
}

output "artifact_bucket_name" {
  description = "S3 bucket holding real generated migration artifacts (inventory, blueprint, Terraform plan)."
  value       = aws_s3_bucket.artifacts.bucket
}
