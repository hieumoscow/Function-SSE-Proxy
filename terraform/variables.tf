variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "fnsse"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastasia"
}

variable "publisher_email" {
  description = "The email address of the owner of the API Management service"
  type        = string
  default     = "admin@contoso.com"
}

variable "publisher_name" {
  description = "The name of the owner of the API Management service"
  type        = string
  default     = "Contoso Admin"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "Production"
    Project     = "FNSSE"
  }
}
