output "run_state_table_name" {
  description = "Name of the RunState DynamoDB table (partition key: runId). Consumed by RunStateRepository (Task 5.2)."
  value       = aws_dynamodb_table.run_state.name
}

output "run_state_table_arn" {
  description = "ARN of the RunState DynamoDB table."
  value       = aws_dynamodb_table.run_state.arn
}

output "run_counters_table_name" {
  description = "Name of the RunCounters DynamoDB table (partition key: runId). Consumed by RunCountersRepository (Task 5.3)."
  value       = aws_dynamodb_table.run_counters.name
}

output "run_counters_table_arn" {
  description = "ARN of the RunCounters DynamoDB table."
  value       = aws_dynamodb_table.run_counters.arn
}

output "gate_ticket_table_name" {
  description = "Name of the GateTicket DynamoDB table (partition key: ticketId, GSI: runId-index). Consumed by GateTicketRepository (Task 5.4)."
  value       = aws_dynamodb_table.gate_ticket.name
}

output "gate_ticket_table_arn" {
  description = "ARN of the GateTicket DynamoDB table."
  value       = aws_dynamodb_table.gate_ticket.arn
}

output "gate_ticket_run_id_gsi_name" {
  description = "Name of the runId GSI on the GateTicket table, used by getPendingGates(runId) (Task 9.3)."
  value       = "runId-index"
}

output "dead_letter_record_table_name" {
  description = "Name of the DeadLetterRecord DynamoDB table (partition key: deadLetterId, GSI: runId-index). Consumed by DeadLetterRecordRepository (Task 5.5)."
  value       = aws_dynamodb_table.dead_letter_record.name
}

output "dead_letter_record_table_arn" {
  description = "ARN of the DeadLetterRecord DynamoDB table."
  value       = aws_dynamodb_table.dead_letter_record.arn
}

output "dead_letter_record_run_id_gsi_name" {
  description = "Name of the runId GSI on the DeadLetterRecord table, used by the list-by-run operation (Task 5.5)."
  value       = "runId-index"
}

output "kms_key_arn" {
  description = "ARN of the KMS key used to encrypt all 4 tables (created by this module, or the existing key passed in via var.kms_key_arn)."
  value       = local.kms_key_arn
}

output "table_arns" {
  description = "Map of all 4 table ARNs keyed by table purpose, for convenient use in IAM policy resource lists (e.g. Task 3.4 agent roles, Lambda execution roles)."
  value = {
    run_state          = aws_dynamodb_table.run_state.arn
    run_counters       = aws_dynamodb_table.run_counters.arn
    gate_ticket        = aws_dynamodb_table.gate_ticket.arn
    dead_letter_record = aws_dynamodb_table.dead_letter_record.arn
  }
}

output "table_names" {
  description = "Map of all 4 table names keyed by table purpose, for convenient use as Python repository (Task 5.2-5.5) config/env vars."
  value = {
    run_state          = aws_dynamodb_table.run_state.name
    run_counters       = aws_dynamodb_table.run_counters.name
    gate_ticket        = aws_dynamodb_table.gate_ticket.name
    dead_letter_record = aws_dynamodb_table.dead_letter_record.name
  }
}
