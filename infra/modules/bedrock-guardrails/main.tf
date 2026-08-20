locals {
  guardrail_name = coalesce(var.guardrail_name, "${var.name_prefix}-guardrail-${var.environment}")

  tags = merge(var.tags, {
    Name        = local.guardrail_name
    Environment = var.environment
    Purpose     = "bedrock-guardrail"
  })
}

# ---------------------------------------------------------------------------
# Bedrock Guardrail
#
# Applied to every agent's Bedrock model calls per Requirement 9.3:
#   - PII redaction/masking            -> sensitive_information_policy_config
#   - Prompt-injection / jailbreak     -> content_policy_config (PROMPT_ATTACK filter)
#   - Denied topics                    -> topic_policy_config
#   - Word/phrase filters              -> word_policy_config
#   - Grounding / relevance checks     -> contextual_grounding_policy_config
# ---------------------------------------------------------------------------

resource "aws_bedrock_guardrail" "this" {
  name                      = local.guardrail_name
  description               = var.description
  blocked_input_messaging   = var.blocked_input_messaging
  blocked_outputs_messaging = var.blocked_outputs_messaging
  kms_key_arn               = var.kms_key_arn

  content_policy_config {
    dynamic "filters_config" {
      for_each = var.content_filters
      content {
        type            = filters_config.value.type
        input_strength  = filters_config.value.input_strength
        output_strength = filters_config.value.output_strength
      }
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = var.pii_entities
      content {
        type   = pii_entities_config.value.type
        action = pii_entities_config.value.action
      }
    }

    dynamic "regexes_config" {
      for_each = var.pii_regexes
      content {
        name        = regexes_config.value.name
        pattern     = regexes_config.value.pattern
        action      = regexes_config.value.action
        description = regexes_config.value.description
      }
    }
  }

  topic_policy_config {
    dynamic "topics_config" {
      for_each = var.denied_topics
      content {
        name       = topics_config.value.name
        definition = topics_config.value.definition
        examples   = topics_config.value.examples
        type       = "DENY"
      }
    }
  }

  word_policy_config {
    dynamic "managed_word_lists_config" {
      for_each = var.managed_word_lists
      content {
        type = managed_word_lists_config.value
      }
    }

    dynamic "words_config" {
      for_each = var.denied_words
      content {
        text = words_config.value
      }
    }
  }

  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = var.grounding_threshold
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = var.relevance_threshold
    }
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Published guardrail version
#
# Agents (Task 13.7) and the pre-invocation hook's attachGuardrails (Task 10.1) reference this
# published version rather than DRAFT, so an in-progress edit to the guardrail's DRAFT config
# never changes behavior for a run already in flight.
# ---------------------------------------------------------------------------

resource "aws_bedrock_guardrail_version" "this" {
  count = var.create_published_version ? 1 : 0

  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = var.guardrail_version_description
  skip_destroy  = var.skip_destroy_on_new_version
}
