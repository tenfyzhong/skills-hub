output "public_ips" {
  description = "Stable public IPv4 addresses grouped by node name."
  value = {
    for group_name in sort(keys(var.node_groups)) : group_name => [
      for key in sort(keys(local.node_instances)) : aws_eip.node[key].public_ip
      if local.node_instances[key].group_name == group_name
    ]
  }
}

output "private_ips" {
  description = "Private IPv4 addresses grouped by node name."
  value = {
    for group_name in sort(keys(var.node_groups)) : group_name => [
      for key in sort(keys(local.node_instances)) : aws_instance.node[key].private_ip
      if local.node_instances[key].group_name == group_name
    ]
  }
}

output "instance_ids" {
  description = "EC2 instance IDs grouped by node name."
  value = {
    for group_name in sort(keys(var.node_groups)) : group_name => [
      for key in sort(keys(local.node_instances)) : aws_instance.node[key].id
      if local.node_instances[key].group_name == group_name
    ]
  }
}

output "instance_types" {
  description = "Resolved EC2 instance type for each node group."
  value = {
    for group_name, group in var.node_groups : group_name => group.instance_type
  }
}

output "ssh_commands" {
  description = "SSH commands grouped by node name."
  value = {
    for group_name in sort(keys(var.node_groups)) : group_name => [
      for key in sort(keys(local.node_instances)) : "ssh ${var.ssh_user}@${aws_eip.node[key].public_ip}"
      if local.node_instances[key].group_name == group_name
    ]
  }
}
