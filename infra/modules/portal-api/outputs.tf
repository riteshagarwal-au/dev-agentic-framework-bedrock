output "api_endpoint" {
  description = "Base invoke URL of the portal HTTP API."
  value       = aws_apigatewayv2_api.portal.api_endpoint
}
