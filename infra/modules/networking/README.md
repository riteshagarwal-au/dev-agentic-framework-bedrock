# networking

Provisions the baseline VPC topology needed to host ECS Fargate tasks and Lambda-backed hooks in
Phase 1's single-account, single-region deployment — the infra prerequisite for Requirement 7.5
(deploying the built container image to ECS Fargate) and, indirectly, Requirement 12.1 (the
portal's start-a-run action, which is served by the Lambda-backed API behind it).

## Topology

```
                         ┌───────────────────────────────────────────────┐
                         │                      VPC                      │
                         │                 (var.vpc_cidr)                 │
                         │                                               │
   Internet ── IGW ──────┤  AZ-a                         AZ-b            │
                         │  ┌───────────────┐   ┌───────────────┐        │
                         │  │ Public subnet │   │ Public subnet │        │
                         │  │  (NAT GW)     │   │  (NAT GW*)    │        │
                         │  └──────┬────────┘   └──────┬────────┘        │
                         │         │ 0.0.0.0/0 via NAT  │                 │
                         │  ┌──────▼────────┐   ┌──────▼────────┐        │
                         │  │ Private subnet│   │ Private subnet│        │
                         │  │ (ECS Fargate, │   │ (ECS Fargate, │        │
                         │  │  Lambda hooks)│   │  Lambda hooks)│        │
                         │  └───────────────┘   └───────────────┘        │
                         └───────────────────────────────────────────────┘
```

`*` only created when `single_nat_gateway = false` (default is `true`: a single shared NAT
Gateway in AZ-a's public subnet, used by every AZ's private route table).

- **VPC** — a single VPC (`var.vpc_cidr`, default `10.0.0.0/16`) with DNS hostnames/resolution
  enabled.
- **Public subnets** — one per AZ (`var.availability_zone_count`, default 2), auto-assigning
  public IPs. Each routes `0.0.0.0/0` to the Internet Gateway via a shared public route table.
  Used for NAT Gateway placement and any other internet-facing resource.
- **Private subnets** — one per AZ, no direct route to the Internet Gateway. Used for ECS Fargate
  tasks and Lambda-backed hooks. Each AZ gets its own route table routing `0.0.0.0/0` to a NAT
  Gateway, so resources in private subnets can reach AWS APIs / the internet (pulling container
  images from ECR, calling Bedrock, etc.) without being directly reachable from the internet.
- **Internet Gateway** — attached to the VPC, referenced by the public route table.
- **NAT Gateway(s)** — by default a single shared NAT Gateway (`single_nat_gateway = true`) in the
  first AZ's public subnet, referenced by every private route table. Set
  `single_nat_gateway = false` to provision one NAT Gateway per AZ instead (higher availability,
  higher cost — not required for Phase 1's scope).

Public and private subnet CIDR ranges are both carved out of `var.vpc_cidr` via `cidrsubnet()`
(public subnets first, private subnets immediately after), so they never overlap regardless of
`var.availability_zone_count`.

## Phase 1 scope boundary

This module intentionally provides only the **baseline** VPC/subnet/routing topology needed to
run ECS Fargate and Lambda in a private subnet with outbound internet/AWS-API access. Per
`requirements.md` "Out of Scope for Phase 1" and `design.md`'s Phase 1/Phase 2 scope table, the
following are **explicitly excluded** here and deferred to Phase 2+:

- **VPC PrivateLink / VPC endpoints** — Phase 1 traffic from private subnets to AWS services
  (ECR, Bedrock, Secrets Manager, DynamoDB, etc.) egresses through the NAT Gateway like normal
  internet-bound traffic; it does not stay on the AWS private network via interface/gateway
  endpoints. VPC/PrivateLink network isolation is not treated as a hard security boundary in
  Phase 1.
- **Cross-account compute topology** — this module provisions networking within a single AWS
  account. Cross-account VPC topologies (e.g. hub-and-spoke, Transit Gateway peering across
  accounts) are out of scope.
- **Multi-region / multi-VPC** — Phase 1 is single-region (see root `infra/variables.tf`
  `aws_region`, default `ap-southeast-2`); this module creates exactly one VPC per invocation.

Security groups scoped to specific workloads (ECS service SG, Lambda SG, etc.) are also **not**
created by this module — they belong to the consuming modules (e.g. Task 14.3's ECS Fargate
target infra) that know the specific ports/protocols each workload needs, using the subnet IDs
output here.

## Usage

```hcl
module "networking" {
  source      = "../../modules/networking"
  environment = var.environment
  name_prefix = "daf-phase1"
  tags        = { Project = var.project_tag }
}
```

Consumers (e.g. the ECS Fargate target module from Task 14.3) use `private_subnet_ids` for
Fargate tasks/Lambda ENIs and `public_subnet_ids`/`vpc_id` for any load balancer or other
internet-facing resource.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; used in resource naming/tags. | `string` | n/a (required) |
| `name_prefix` | Prefix applied to every resource name/tag. | `string` | `"daf-phase1"` |
| `vpc_cidr` | CIDR block for the VPC. | `string` | `"10.0.0.0/16"` |
| `availability_zone_count` | Number of AZs to spread subnets across (>= 2). | `number` | `2` |
| `public_subnet_newbits` | Additional bits for public subnet CIDRs via `cidrsubnet()`. | `number` | `8` |
| `private_subnet_newbits` | Additional bits for private subnet CIDRs via `cidrsubnet()`. | `number` | `8` |
| `single_nat_gateway` | Use one shared NAT Gateway instead of one per AZ. | `bool` | `true` |
| `enable_dns_hostnames` | Enable DNS hostnames in the VPC. | `bool` | `true` |
| `enable_dns_support` | Enable DNS resolution in the VPC. | `bool` | `true` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `vpc_id` | ID of the VPC. |
| `vpc_cidr_block` | CIDR block of the VPC. |
| `public_subnet_ids` | IDs of the public subnets (one per AZ). |
| `private_subnet_ids` | IDs of the private subnets (one per AZ) — consumed by Task 14.3's ECS Fargate target infra. |
| `availability_zones` | AZs used, in the same order as the subnet ID lists. |
| `internet_gateway_id` | ID of the Internet Gateway. |
| `nat_gateway_ids` | IDs of the NAT Gateway(s). |
| `public_route_table_id` | ID of the shared public route table. |
| `private_route_table_ids` | IDs of the private route tables (one per AZ). |

## Requirements traceability

- Infra prerequisite for Requirement 7.5: "WHEN a human approves the cloud-deploy gate THEN
  GitHub Actions SHALL deploy the built container image to ECS Fargate." — this module provides
  the VPC/subnets the ECS Fargate target infra (Task 14.3) deploys into.
- Infra prerequisite for Requirement 12.1: "THE portal SHALL allow an authenticated user to start
  a new migration run..." — the private subnets here are where the Lambda-backed API behind that
  portal action (Task 17.1) runs.
