locals {
  name = "${var.name_prefix}-${var.environment}"

  common_tags = merge(var.tags, {
    Environment = var.environment
  })

  az_count = var.availability_zone_count
  azs      = slice(data.aws_availability_zones.available.names, 0, local.az_count)

  # Public subnets are carved first (index 0..az_count-1), private subnets follow immediately
  # after in the same address space (index az_count..2*az_count-1), so the two ranges never
  # overlap regardless of how many AZs are requested.
  public_subnet_cidrs = [
    for i in range(local.az_count) : cidrsubnet(var.vpc_cidr, var.public_subnet_newbits, i)
  ]
  private_subnet_cidrs = [
    for i in range(local.az_count) : cidrsubnet(var.vpc_cidr, var.private_subnet_newbits, local.az_count + i)
  ]

  # Number of NAT Gateways to create: 1 if single_nat_gateway = true, otherwise one per AZ.
  nat_gateway_count = var.single_nat_gateway ? 1 : local.az_count
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = var.enable_dns_hostnames
  enable_dns_support   = var.enable_dns_support

  tags = merge(local.common_tags, {
    Name = local.name
  })
}

# ---------------------------------------------------------------------------
# Internet Gateway (public subnet egress)
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name}-igw"
  })
}

# ---------------------------------------------------------------------------
# Public subnets — one per AZ, auto-assign public IPs, used for the NAT
# Gateway(s) and any other internet-facing resources.
# ---------------------------------------------------------------------------

resource "aws_subnet" "public" {
  count = local.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${local.name}-public-${local.azs[count.index]}"
    Tier = "public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name}-public-rt"
    Tier = "public"
  })
}

resource "aws_route" "public_internet_access" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = local.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ---------------------------------------------------------------------------
# Private subnets — one per AZ, host ECS Fargate tasks and Lambda-backed
# hooks. No direct route to the Internet Gateway; egress only via NAT.
# ---------------------------------------------------------------------------

resource "aws_subnet" "private" {
  count = local.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_subnet_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = merge(local.common_tags, {
    Name = "${local.name}-private-${local.azs[count.index]}"
    Tier = "private"
  })
}

# ---------------------------------------------------------------------------
# NAT Gateway(s) — deployed in public subnet(s) so private-subnet ECS
# Fargate tasks / Lambda functions can reach AWS APIs and the internet
# (e.g. pulling container images, calling Bedrock).
# ---------------------------------------------------------------------------

resource "aws_eip" "nat" {
  count = local.nat_gateway_count

  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name}-nat-eip-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count = local.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  # Place each NAT Gateway in the public subnet of the corresponding AZ (or AZ 0 when
  # single_nat_gateway = true, since there's only one to place).
  subnet_id = aws_subnet.public[count.index].id

  tags = merge(local.common_tags, {
    Name = "${local.name}-nat-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

# ---------------------------------------------------------------------------
# Private route tables — one per AZ so each private subnet can route
# 0.0.0.0/0 to its own AZ's NAT Gateway (or the single shared one).
# ---------------------------------------------------------------------------

resource "aws_route_table" "private" {
  count = local.az_count

  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name}-private-rt-${local.azs[count.index]}"
    Tier = "private"
  })
}

resource "aws_route" "private_nat_access" {
  count = local.az_count

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  # When single_nat_gateway = true there is only aws_nat_gateway.this[0]; every private route
  # table points at it. Otherwise each AZ's private route table points at its own NAT Gateway.
  nat_gateway_id = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "private" {
  count = local.az_count

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
