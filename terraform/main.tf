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
  use_cli = true
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
  local_user_enabled              = false
  shared_access_key_enabled       = true
  
  min_tls_version                = "TLS1_2"
  allow_nested_items_to_be_public = false
  
  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# Storage container for deployment package
resource "azurerm_storage_container" "deployment" {
  name                  = "deployment"
  storage_account_name  = azurerm_storage_account.sa.name
  container_access_type = "private"
}

# Grant current user Storage Blob Data Owner role
data "azurerm_client_config" "current" {}

resource "azurerm_role_assignment" "current_user_storage" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

# App Service Plan
resource "azapi_resource" "asp" {
  type                      = "Microsoft.Web/serverfarms@2023-12-01"
  name                      = "asp-${var.project_name}-${random_string.suffix.result}"
  parent_id                 = azurerm_resource_group.rg.id
  location                  = azurerm_resource_group.rg.location
  schema_validation_enabled = false

  body = jsonencode({
    kind = "functionapp"
    sku = {
      tier = "FlexConsumption"
      name = "FC1"
    }
    properties = {
      reserved = true
    }
  })

  tags = var.tags
}

# Function App
resource "azapi_resource" "func" {
  type                      = "Microsoft.Web/sites@2023-12-01"
  name                      = "func-${var.project_name}-${random_string.suffix.result}"
  parent_id                 = azurerm_resource_group.rg.id
  location                  = azurerm_resource_group.rg.location
  schema_validation_enabled = false

  body = jsonencode({
    kind = "functionapp,linux"
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      serverFarmId = azapi_resource.asp.id
      functionAppConfig = {
        deployment = {
          storage = {
            type = "blobContainer"
            value = "${azurerm_storage_account.sa.primary_blob_endpoint}${azurerm_storage_container.deployment.name}"
            authentication = {
              type = "SystemAssignedIdentity"
            }
          }
        }
        scaleAndConcurrency = {
          maximumInstanceCount = 40
          instanceMemoryMB = 2048
        }
        runtime = {
          name = "python"
          version = "3.11"
        }
      }
      siteConfig = {
        appSettings = [
          {
            name  = "FUNCTION_APP_URL"
            value = "https://func-${var.project_name}-${random_string.suffix.result}.azurewebsites.net"
          },
          {
            name  = "AZURE_EVENTHUB_NAME"
            value = azurerm_eventhub.eh.name
          },
          {
            name  = "AZURE_EVENTHUB_NAMESPACE"
            value = azurerm_eventhub_namespace.ehns.name
          },
          {
            name  = "AZURE_EVENTHUB_CONN_STR"
            value = azurerm_eventhub_authorization_rule.eh_rule.primary_connection_string
          },
          {
            name  = "COSMOS_ENDPOINT"
            value = azurerm_cosmosdb_account.cosmos.endpoint
          },
          {
            name  = "WEBSITES_ENABLE_APP_SERVICE_STORAGE"
            value = "false"
          },
          {
            name  = "PYTHON_ENABLE_INIT_INDEXING"
            value = "1"
          },
          {
            name  = "AzureWebJobsStorage__accountName"
            value = azurerm_storage_account.sa.name
          },
          {
            name  = "AzureWebJobsStorage"
            value = azurerm_storage_account.sa.primary_connection_string
          },
          {
            name  = "FUNCTIONS_EXTENSION_VERSION"
            value = "~4"
          },
          {
            name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
            value = azurerm_application_insights.appinsights.connection_string
          },
          {
            name  = "APPINSIGHTS_INSTRUMENTATIONKEY"
            value = azurerm_application_insights.appinsights.instrumentation_key
          },
          {
            name  = "ApplicationInsightsAgent_EXTENSION_VERSION"
            value = "~3"
          },
          {
            name  = "AZURE_OPENAI_KEY"
            value = ""
          },
          {
            name  = "AZURE_OPENAI_API_VERSION"
            value = "2024-08-01-preview"
          },
          {
            name  = "AZURE_OPENAI_BASE_URL"
            value = "https://<your-instance>.openai.azure.com/"
          },
          {
            name  = "AZURE_OPENAI_MODEL"
            value = "gpt-4o"
          }
        ]
      }
    }
  })

  tags = var.tags
  depends_on = [azapi_resource.asp, azurerm_application_insights.appinsights, azurerm_storage_account.sa]
}

# Get Function App details for role assignments
data "azurerm_linux_function_app" "func_wrapper" {
  name                = azapi_resource.func.name
  resource_group_name = azurerm_resource_group.rg.name
}

# Grant Function App necessary storage roles
resource "azurerm_role_assignment" "func_storage_blob" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_storage_queue" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_storage_table" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
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

# Grant Function App access to Event Hub Data Sender role
resource "azurerm_role_assignment" "func_eventhub" {
  scope                = azurerm_eventhub.eh.id
  role_definition_name = "Azure Event Hubs Data Sender"
  principal_id         = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
}

# Grant Function App access to Event Hub Data Receiver role
resource "azurerm_role_assignment" "func_eventhub_receiver" {
  scope                = azurerm_eventhub.eh.id
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
}

# Cosmos DB Account
resource "azurerm_cosmosdb_account" "cosmos" {
  name                = "cosmos-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  local_authentication_disabled = true

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
  name                = "ApimAOAI"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

# Cosmos DB Container for APIM AOAI
resource "azurerm_cosmosdb_sql_container" "container" {
  name                = "ApimAOAI"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/id"]
}

# Cosmos DB Container for User Budgets
resource "azurerm_cosmosdb_sql_container" "user_budgets" {
  name                = "UserBudgets"
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
  principal_id        = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
  scope              = azurerm_cosmosdb_account.cosmos.id
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "law" {
  name                = "law-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

# Virtual Network for APIM
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.0.0.0/16"]
  tags                = var.tags
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

# APIM Logger for App Insights
resource "azapi_resource" "apim_logger" {
  type      = "Microsoft.ApiManagement/service/loggers@2023-09-01-preview"
  name      = "appinsights"
  parent_id = azapi_resource.apim.id

  body = jsonencode({
    properties = {
      loggerType             = "applicationInsights"
      description           = "Logger resources for API Management"
      resourceId            = azurerm_application_insights.appinsights.id
      credentials = {
        instrumentationKey = azurerm_application_insights.appinsights.instrumentation_key
      }
    }
  })
}

# Application Insights
resource "azurerm_application_insights" "appinsights" {
  name                = "appi-${var.project_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.law.id
  tags                = var.tags
}
