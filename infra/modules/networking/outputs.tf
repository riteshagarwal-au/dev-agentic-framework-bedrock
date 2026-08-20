output "vpc_id" {
  description = "ID of the VPC created by this module."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC created by this module."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (one per AZ), suitable for internet-facing resources and NAT Gateway placement."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (one per AZ), used for ECS Fargate tasks and Lambda-backed hooks."
  value       = aws_subnet.private[*].id
}

output "availability_zones" {
  description = "Availability Zones used for the public/private subnet pairs, in the same order as the subnet ID lists."
  value       = local.azs
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway attached to the VPC."
  value       = aws_internet_gateway.this.id
}

output "nat_gateway_ids" {
  description = "IDs of the NAT Gateway(s) created by this module (length 1 when single_nat_gateway = true, otherwise one per AZ)."
  value       = aws_nat_gateway.this[*].id
}

output "public_route_table_id" {
  description = "ID of the public subnets' shared route table."
  value       = aws_route_table.public.id
}

output "private_route_table_ids" {
  description = "IDs of the private subnets' route tables (one per AZ)."
  value       = aws_route_table.private[*].id
}
