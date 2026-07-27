variable "namespace" {
  description = "Prefix used for AWS resource names and tags."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,62}$", var.namespace))
    error_message = "namespace must contain 1-63 lowercase letters, digits, or hyphens."
  }
}

variable "aws_profile" {
  description = "AWS CLI profile used by the provider."
  type        = string
  default     = "default"
}

variable "region" {
  description = "AWS region in which to deploy the nodes."
  type        = string
  default     = "us-west-2"
}

variable "availability_zone" {
  description = "Optional availability zone. The first available zone is used when null."
  type        = string
  default     = null
}

variable "vpc_cidr" {
  description = "CIDR block for the deployment VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet."
  type        = string
  default     = "10.0.0.0/20"
}

variable "ssh_cidr" {
  description = "IPv4 CIDR allowed to connect to TCP port 22."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0)) && !strcontains(var.ssh_cidr, ":")
    error_message = "ssh_cidr must be an IPv4 CIDR."
  }
}

variable "public_key_path" {
  description = "Path to the SSH public key registered with EC2."
  type        = string
}

variable "ssh_user" {
  description = "SSH user provided by the selected AMI."
  type        = string
  default     = "ec2-user"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size >= 8
    error_message = "root_volume_size must be at least 8 GiB."
  }
}

variable "node_groups" {
  description = "Named EC2 node groups with resolved instance types."
  type = map(object({
    count         = number
    cpu           = number
    memory_gib    = number
    instance_type = string
  }))

  validation {
    condition = length(var.node_groups) > 0 && alltrue([
      for group in values(var.node_groups) :
      group.count > 0 && group.cpu > 0 && group.memory_gib > 0
    ])
    error_message = "node_groups must contain at least one group with positive count, CPU, and memory."
  }
}
