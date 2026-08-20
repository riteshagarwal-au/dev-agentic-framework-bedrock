output "bucket_name" {
  description = "Name of the S3 bucket the portal's built static assets are uploaded to."
  value       = aws_s3_bucket.portal.id
}

output "distribution_id" {
  description = "CloudFront distribution ID, used for cache invalidation after each deploy."
  value       = aws_cloudfront_distribution.portal.id
}

output "distribution_domain_name" {
  description = "CloudFront distribution domain — the DAF Portal's public URL."
  value       = aws_cloudfront_distribution.portal.domain_name
}

output "portal_url" {
  description = "Full HTTPS URL of the deployed DAF Portal."
  value       = "https://${aws_cloudfront_distribution.portal.domain_name}"
}
