# ECS Fargate hosting for the target/synthetic migrated app (design.md §7.3, §14 line 418:
# "Phase 1: single account ... hosts compute (ECS Fargate)").
#
# This module owns the SHARED platform compute the target app is deployed onto (cluster, ECR
# repo, task execution role, initial task definition/service placeholder). It is deliberately
# separate from the target app's own repo, which only ever supplies a container image + task
# definition revision via its `container-deploy.yml` CI/CD pipeline (gated by
# HitlGateType.CLOUD_DEPLOY) — the target app's CI never creates/destroys the cluster itself.
#
# In a future multi-tenant Phase 2+, each tenant would get its own cluster/account rather than
# sharing this one; Phase 1 is explicitly single-account/single-tenant per design.md.

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_ecs_cluster" "target" {
  name = "${var.name_prefix}-target-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, { Environment = var.environment })
}

resource "aws_ecr_repository" "target" {
  name                 = "${var.name_prefix}-target-${var.environment}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.tags, { Environment = var.environment })
}

resource "aws_security_group" "target_tasks" {
  name_prefix = "${var.name_prefix}-target-tasks-"
  description = "ECS Fargate tasks running the migrated target app."
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound (image pull, AWS API calls)."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Allow inbound to the container port from within the VPC only (Phase 1 has no public ALB)."
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.this.cidr_block]
  }

  tags = merge(var.tags, { Environment = var.environment })
}

data "aws_vpc" "this" {
  id = var.vpc_id
}

resource "aws_iam_role" "task_execution" {
  name = "${var.name_prefix}-target-task-exec-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, { Environment = var.environment })
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_cloudwatch_log_group" "target" {
  name              = "/ecs/${var.name_prefix}-target-${var.environment}"
  retention_in_days = 30

  tags = merge(var.tags, { Environment = var.environment })
}

# Placeholder task definition (Phase 1 bootstrap only). The target app's own CI/CD pipeline
# (container-deploy.yml, in the target app's own repo) registers real revisions of this family
# and updates the service — Terraform only owns the family name / execution role here so the
# github-oidc CI/CD role has a stable set of ARNs to scope IAM permissions against.
resource "aws_ecs_task_definition" "target" {
  family                   = "${var.name_prefix}-target-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([{
    name      = "target-app"
    image     = "${aws_ecr_repository.target.repository_url}:bootstrap"
    essential = true
    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.target.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "target-app"
      }
    }
  }])

  tags = merge(var.tags, { Environment = var.environment })

  lifecycle {
    # The target app's own deploy pipeline registers new task definition revisions directly;
    # Terraform should not fight over container_definitions/image after the bootstrap revision.
    ignore_changes = [container_definitions]
  }
}

resource "aws_ecs_service" "target" {
  name            = "${var.name_prefix}-target-${var.environment}"
  cluster         = aws_ecs_cluster.target.id
  task_definition = aws_ecs_task_definition.target.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.target_tasks.id]
  }

  tags = merge(var.tags, { Environment = var.environment })

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}
