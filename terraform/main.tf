terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 1.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.0"
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azapi" {}

# Generate random suffix
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.project_name}-${random_string.suffix.result}"
  location = var.location
  tags     = var.tags
}

# Storage Account for Function App
resource "azurerm_storage_account" "sa" {
  name                            = "${var.project_name}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                           = var.tags
}

# App Service Plan
resource "azurerm_service_plan" "asp" {
  name                = "asp-${var.project_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location           = azurerm_resource_group.rg.location
  os_type            = "Linux"
  sku_name           = "Y1" # Consumption plan

  tags = var.tags
}

# Function App
resource "azurerm_linux_function_app" "func" {
  name                = "func-${var.project_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location           = azurerm_resource_group.rg.location

  storage_account_name       = azurerm_storage_account.sa.name
  storage_account_access_key = azurerm_storage_account.sa.primary_access_key
  service_plan_id           = azurerm_service_plan.asp.id

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.10"
    }
    minimum_tls_version = "1.2"
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME"     = "python"
    "AZURE_EVENTHUB_NAME"         = azurerm_eventhub.eh.name
    "AZURE_EVENTHUB_NAMESPACE"    = azurerm_eventhub_namespace.ehns.name
    "COSMOS_ENDPOINT"             = azurerm_cosmosdb_account.cosmos.endpoint
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
    "PYTHON_ENABLE_INIT_INDEXING" = "1"
  }

  tags = var.tags
}

# Event Hub Namespace
resource "azurerm_eventhub_namespace" "ehns" {
  name                = "ehns-${var.project_name}-${random_string.suffix.result}"
  location           = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                = "Standard"
  capacity           = 1

  tags = var.tags
}

# Event Hub
resource "azurerm_eventhub" "eh" {
  name                = "eh-${var.project_name}-${random_string.suffix.result}"
  namespace_name      = azurerm_eventhub_namespace.ehns.name
  resource_group_name = azurerm_resource_group.rg.name
  partition_count     = 2
  message_retention   = 1
}

# Event Hub Authorization Rule
resource "azurerm_eventhub_authorization_rule" "eh_rule" {
  name                = "SendPolicy"
  namespace_name      = azurerm_eventhub_namespace.ehns.name
  eventhub_name       = azurerm_eventhub.eh.name
  resource_group_name = azurerm_resource_group.rg.name
  listen              = false
  send                = true
  manage              = false
}

# Cosmos DB Account
resource "azurerm_cosmosdb_account" "cosmos" {
  name                = "cosmos-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  automatic_failover_enabled = false
  
  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level       = "Session"
    max_interval_in_seconds = 5
    max_staleness_prefix    = 100
  }

  geo_location {
    location          = azurerm_resource_group.rg.location
    failover_priority = 0
  }

  tags = var.tags
}

# Cosmos DB SQL Database
resource "azurerm_cosmosdb_sql_database" "db" {
  name                = "db-${var.project_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

# Cosmos DB Container
resource "azurerm_cosmosdb_sql_container" "container" {
  name                = "container-${var.project_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/id"]
}

# Grant Function App access to Cosmos DB
resource "azurerm_cosmosdb_sql_role_assignment" "func_cosmos_role" {
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002" # Built-in Data Contributor role
  principal_id        = azurerm_linux_function_app.func.identity[0].principal_id
  scope              = azurerm_cosmosdb_account.cosmos.id
}


# Grant Function App access to Event Hub Data Sender role
resource "azurerm_role_assignment" "func_eventhub" {
  scope                = azurerm_eventhub.eh.id
  role_definition_name = "Azure Event Hubs Data Sender"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

# Grant Function App access to Event Hub Data Receiver role
resource "azurerm_role_assignment" "func_eventhub_receiver" {
  scope                = azurerm_eventhub.eh.id
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

# Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.0.0.0/16"]

  tags = var.tags
}

# Subnet for APIM
resource "azurerm_subnet" "apim_subnet" {
  name                 = "snet-apim-${random_string.suffix.result}"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
  
  private_endpoint_network_policies = "Enabled"

  delegation {
    name = "serverfarms-delegation"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# Network Security Group for APIM
resource "azurerm_network_security_group" "apim_nsg" {
  name                = "nsg-apim-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  security_rule {
    name                       = "APIM_Management_Endpoint"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3443"
    source_address_prefix      = "ApiManagement"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "APIM_Gateway"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "VirtualNetwork"
  }

  tags = var.tags
}

# Associate NSG with APIM subnet
resource "azurerm_subnet_network_security_group_association" "apim_nsg_association" {
  subnet_id                 = azurerm_subnet.apim_subnet.id
  network_security_group_id = azurerm_network_security_group.apim_nsg.id
}

# Public IP for APIM
resource "azurerm_public_ip" "apim_pip" {
  name                = "pip-apim-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location           = azurerm_resource_group.rg.location
  allocation_method  = "Static"
  sku               = "Standard"
  domain_name_label = "apim-${var.project_name}-${random_string.suffix.result}"
  
  tags = var.tags
}

# APIM Standard v2
resource "azapi_resource" "apim" {
  type      = "Microsoft.ApiManagement/service@2023-09-01-preview"
  name      = "apim-${var.project_name}-${random_string.suffix.result}"
  location  = azurerm_resource_group.rg.location
  parent_id = azurerm_resource_group.rg.id

  body = jsonencode({
    properties = {
      publisherEmail = var.publisher_email
      publisherName  = var.publisher_name
      virtualNetworkType = "External"
      virtualNetworkConfiguration = {
        subnetResourceId = azurerm_subnet.apim_subnet.id
      }
      publicIpAddressId = azurerm_public_ip.apim_pip.id
    }
    sku = {
      name = "StandardV2"
      capacity = 1
    }
  })

  depends_on = [
    azurerm_subnet_network_security_group_association.apim_nsg_association
  ]

  tags = var.tags
}
