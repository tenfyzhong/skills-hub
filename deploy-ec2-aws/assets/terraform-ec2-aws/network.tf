data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  availability_zone = coalesce(var.availability_zone, data.aws_availability_zones.available.names[0])
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.namespace}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.namespace}-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = local.availability_zone
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.namespace}-public"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.namespace}-public"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "nodes" {
  name_prefix = "${var.namespace}-nodes-"
  description = "SSH ingress and unrestricted traffic among deployment nodes"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.namespace}-nodes"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "ssh" {
  type              = "ingress"
  description       = "SSH from the operator CIDR"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.ssh_cidr]
  security_group_id = aws_security_group.nodes.id
}

resource "aws_security_group_rule" "internal" {
  type              = "ingress"
  description       = "All traffic among nodes in this deployment"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  self              = true
  security_group_id = aws_security_group.nodes.id
}

resource "aws_security_group_rule" "egress" {
  type              = "egress"
  description       = "Unrestricted outbound traffic"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.nodes.id
}
