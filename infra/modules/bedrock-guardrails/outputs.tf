output "guardrail_id" {
  description = "ID of the Bedrock Guardrail (the DRAFT working copy's identifier, stable across versions)."
  value       = aws_bedrock_guardrail.this.guardrail_id
}

output "guardrail_arn" {
  description = "ARN of the Bedrock Guardrail."
  value       = aws_bedrock_guardrail.this.guardrail_arn
}

output "guardrail_draft_version" {
  description = "Version string of the guardrail's DRAFT working copy (always \"DRAFT\")."
  value       = aws_bedrock_guardrail.this.version
}

output "guardrail_published_version" {
  description = <<-EOT
    Version number of the published, immutable guardrail version created by this module (e.g.
    "1"), or null when create_published_version = false. Task 13.7's Bedrock Agent resources and
    the pre-invocation hook's attachGuardrails (Task 10.1) should reference this stable version
    rather than the DRAFT version above.
  EOT
  value       = var.create_published_version ? aws_bedrock_guardrail_version.this[0].version : null
}

output "guardrail_status" {
  description = "Status of the Bedrock Guardrail (READY or FAILED)."
  value       = aws_bedrock_guardrail.this.status
}
