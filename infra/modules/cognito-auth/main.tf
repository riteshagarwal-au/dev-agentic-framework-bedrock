# Cognito auth for the DAF Portal (design.md §14: "React SPA on S3 + CloudFront, API Gateway +
# Lambda backend, Cognito auth"). A JWT authorizer on the portal-api's HTTP API validates tokens
# issued by this User Pool (Requirement 12.4's authenticated-caller check in handlers.py is a
# defense-in-depth backstop for this).

data "aws_region" "current" {}

resource "aws_cognito_user_pool" "portal" {
  name = "${var.name_prefix}-portal-${var.environment}"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  tags = { Environment = var.environment }
}

resource "aws_cognito_user_pool_domain" "portal" {
  domain       = "${var.name_prefix}-portal-${var.environment}"
  user_pool_id = aws_cognito_user_pool.portal.id
}

resource "aws_cognito_user_pool_client" "portal_spa" {
  name         = "${var.name_prefix}-portal-spa-${var.environment}"
  user_pool_id = aws_cognito_user_pool.portal.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls

  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
