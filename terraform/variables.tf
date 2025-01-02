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

variable "azure_openai_key" {
  description = "Azure OpenAI API Key"
  type        = string
  sensitive   = true
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API Version"
  type        = string
}

variable "azure_openai_base_url" {
  description = "Azure OpenAI Base URL"
  type        = string
}

variable "azure_openai_model" {
  description = "Azure OpenAI Model Name"
  type        = string
}
