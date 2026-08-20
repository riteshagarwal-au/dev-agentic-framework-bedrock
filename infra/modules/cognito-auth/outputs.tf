output "user_pool_id" {
  description = "ID of the Cognito User Pool backing portal auth."
  value       = aws_cognito_user_pool.portal.id
}

output "user_pool_arn" {
  description = "ARN of the Cognito User Pool, used by the API Gateway JWT authorizer."
  value       = aws_cognito_user_pool.portal.arn
}

output "user_pool_client_id" {
  description = "ID of the SPA's Cognito app client (no client secret, public client)."
  value       = aws_cognito_user_pool_client.portal_spa.id
}

output "user_pool_domain" {
  description = "Cognito Hosted UI domain prefix used for the OAuth login/logout flow."
  value       = aws_cognito_user_pool_domain.portal.domain
}

output "issuer_url" {
  description = "OIDC issuer URL for the API Gateway JWT authorizer."
  value       = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.portal.id}"
}
