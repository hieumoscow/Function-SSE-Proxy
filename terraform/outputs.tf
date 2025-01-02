output "resource_group_name" {
  value = azurerm_resource_group.rg.name
}

output "function_app_name" {
  value = azapi_resource.func.name
}

output "function_app_default_hostname" {
  value = data.azurerm_linux_function_app.func_wrapper.default_hostname
}

output "storage_account_name" {
  value = azurerm_storage_account.sa.name
}

output "storage_account_primary_access_key" {
  value     = azurerm_storage_account.sa.primary_access_key
  sensitive = true
}

output "eventhub_name" {
  value = azurerm_eventhub.eh.name
}

output "eventhub_namespace" {
  value = azurerm_eventhub_namespace.ehns.name
}

output "eventhub_connection_string" {
  value     = azurerm_eventhub_authorization_rule.eh_rule.primary_connection_string
  sensitive = true
}

output "cosmos_db_endpoint" {
  value = azurerm_cosmosdb_account.cosmos.endpoint
}

output "cosmos_db_primary_key" {
  value     = azurerm_cosmosdb_account.cosmos.primary_key
  sensitive = true
}

output "application_insights_connection_string" {
  value     = azurerm_application_insights.appinsights.connection_string
  sensitive = true
}

output "application_insights_instrumentation_key" {
  value     = azurerm_application_insights.appinsights.instrumentation_key
  sensitive = true
}

output "function_app_principal_id" {
  value = data.azurerm_linux_function_app.func_wrapper.identity[0].principal_id
}

output "deployment_storage_container_url" {
  value = "${azurerm_storage_account.sa.primary_blob_endpoint}${azurerm_storage_container.deployment.name}"
}

output "apim_name" {
  value = azapi_resource.apim.name
}

output "apim_public_ip" {
  value = azurerm_public_ip.apim_pip.ip_address
}

output "apim_gateway_url" {
  value = "https://${azapi_resource.apim.name}.azure-api.net"
}
