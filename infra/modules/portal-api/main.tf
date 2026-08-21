# Portal API: HTTP API (API Gateway v2) + JWT authorizer (Cognito) + 4 Lambda functions wrapping
# daf.portal_api.lambda_entrypoints (design.md §14: "API Gateway + Lambda backend").
#
# Packaging: each Lambda shares one deployment zip (the `daf` package + its runtime
# dependencies) — built by merging backend_src_dir and backend_site_packages_dir into a staging
# directory via a null_resource, then zipped by the archive provider. Rebuilds whenever the
# source tree's content hash changes.

locals {
  staging_dir = "${path.module}/.build/${var.environment}"
  zip_path    = "${path.module}/.build/${var.environment}.zip"
}

resource "null_resource" "build_lambda_package" {
  triggers = {
    src_hash = sha1(join("", [for f in fileset(var.backend_src_dir, "**/*.py") : filesha1("${var.backend_src_dir}/${f}")]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${local.staging_dir}"
      mkdir -p "${local.staging_dir}"
      cp -R "${var.backend_src_dir}/." "${local.staging_dir}/"
      if [ -d "${var.backend_site_packages_dir}" ]; then
        cp -R "${var.backend_site_packages_dir}/." "${local.staging_dir}/"
      fi
    EOT
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = local.staging_dir
  output_path = local.zip_path
  depends_on  = [null_resource.build_lambda_package]
}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.name_prefix}-portal-api-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Environment = var.environment }
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.name_prefix}-portal-api-artifacts-${var.environment}-${data.aws_caller_identity.current.account_id}"
  tags   = { Environment = var.environment }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lambda_dynamodb_stepfunctions" {
  statement {
    sid    = "RunStateAndCountersAndGateTicketAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      var.run_state_table_arn,
      var.run_counters_table_arn,
      var.gate_ticket_table_arn,
      "${var.gate_ticket_table_arn}/index/*",
    ]
  }

  statement {
    sid       = "HitlStateMachineTaskTokenCallbacks"
    effect    = "Allow"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = [var.hitl_state_machine_arn]
  }

  statement {
    sid       = "InvokeRunWorker"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.run_worker.arn]
  }

  statement {
    sid       = "DynamoDbTableEncryptionKeyAccess"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = [var.dynamodb_kms_key_arn]
  }

  statement {
    sid       = "ArtifactBucketReadWrite"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }

  statement {
    sid       = "StsGetCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_dynamodb_stepfunctions" {
  name   = "${var.name_prefix}-portal-api-lambda-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_dynamodb_stepfunctions.json
}

locals {
  common_env = {
    RUN_STATE_TABLE_NAME    = var.run_state_table_name
    RUN_COUNTERS_TABLE_NAME = var.run_counters_table_name
    GATE_TICKET_TABLE_NAME  = var.gate_ticket_table_name
    HITL_STATE_MACHINE_ARN  = var.hitl_state_machine_arn
    WORKER_FUNCTION_NAME    = aws_lambda_function.run_worker.function_name
    ARTIFACT_BUCKET_NAME    = aws_s3_bucket.artifacts.bucket
  }

  routes = {
    start_run = {
      handler = "daf.portal_api.lambda_entrypoints.start_run"
      method  = "POST"
      path    = "/runs"
    }
    get_run_status = {
      handler = "daf.portal_api.lambda_entrypoints.get_run_status"
      method  = "GET"
      path    = "/runs/{runId}/status"
    }
    list_pending_gates = {
      handler = "daf.portal_api.lambda_entrypoints.list_pending_gates"
      method  = "GET"
      path    = "/runs/{runId}/gates"
    }
    decide_gate = {
      handler = "daf.portal_api.lambda_entrypoints.decide_gate"
      method  = "POST"
      path    = "/gates/{ticketId}/decide"
    }
  }
}

resource "aws_lambda_function" "run_worker" {
  function_name    = "${var.name_prefix}-portal-api-run-worker-${var.environment}"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "daf.portal_api.orchestrator.run_worker_handler"
  runtime          = "python3.12"
  timeout          = var.run_worker_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      RUN_STATE_TABLE_NAME    = var.run_state_table_name
      RUN_COUNTERS_TABLE_NAME = var.run_counters_table_name
      GATE_TICKET_TABLE_NAME  = var.gate_ticket_table_name
      HITL_STATE_MACHINE_ARN  = var.hitl_state_machine_arn
      ARTIFACT_BUCKET_NAME    = aws_s3_bucket.artifacts.bucket
    }
  }

  tags = { Environment = var.environment }
}

resource "aws_lambda_function" "route" {
  for_each = local.routes

  function_name    = "${var.name_prefix}-portal-api-${each.key}-${var.environment}"
  role             = aws_iam_role.lambda_exec.arn
  handler          = each.value.handler
  runtime          = "python3.12"
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = local.common_env
  }

  tags = { Environment = var.environment }
}

resource "aws_apigatewayv2_api" "portal" {
  name          = "${var.name_prefix}-portal-api-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.cors_allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Authorization", "Content-Type"]
  }
}

resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.portal.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-cognito-jwt-${var.environment}"

  jwt_configuration {
    audience = [var.cognito_user_pool_client_id]
    issuer   = var.cognito_issuer_url
  }
}

resource "aws_apigatewayv2_integration" "route" {
  for_each = local.routes

  api_id                 = aws_apigatewayv2_api.portal.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.route[each.key].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "route" {
  for_each = local.routes

  api_id             = aws_apigatewayv2_api.portal.id
  route_key          = "${each.value.method} ${each.value.path}"
  target             = "integrations/${aws_apigatewayv2_integration.route[each.key].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
}

resource "aws_lambda_permission" "apigw_invoke" {
  for_each = local.routes

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.route[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.portal.execution_arn}/*/*"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.portal.id
  name        = "$default"
  auto_deploy = true
}
