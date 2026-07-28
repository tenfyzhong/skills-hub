data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  node_instances = merge([
    for group_name, group in var.node_groups : {
      for index in range(group.count) :
      "${group_name}-${format("%02d", index + 1)}" => {
        instance_name = group.count == 1 ? group_name : "${group_name}-${format("%02d", index + 1)}"
        group_name    = group_name
        index         = index + 1
        cpu           = group.cpu
        memory_gib    = group.memory_gib
        instance_type = group.instance_type
      }
    }
  ]...)
}

resource "aws_key_pair" "deployer" {
  key_name_prefix = "${var.namespace}-"
  public_key      = trimspace(file(pathexpand(var.public_key_path)))

  tags = {
    Name = "${var.namespace}-key"
  }
}

resource "aws_instance" "node" {
  for_each = local.node_instances

  ami                         = nonsensitive(data.aws_ssm_parameter.al2023_ami.value)
  instance_type               = each.value.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.nodes.id]
  key_name                    = aws_key_pair.deployer.key_name
  associate_public_ip_address = false

  root_block_device {
    encrypted             = true
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name               = each.value.instance_name
    NodeGroup          = each.value.group_name
    RequestedCPU       = tostring(each.value.cpu)
    RequestedMemoryGiB = tostring(each.value.memory_gib)
  }

  depends_on = [aws_route_table_association.public]
}

resource "aws_eip" "node" {
  for_each = local.node_instances

  domain   = "vpc"
  instance = aws_instance.node[each.key].id

  tags = {
    Name      = "${var.namespace}-${each.key}"
    NodeGroup = each.value.group_name
  }

  depends_on = [aws_internet_gateway.main]
}
