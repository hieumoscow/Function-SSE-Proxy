output "function_app_name" {
  value = azurerm_linux_function_app.func.name
}

output "function_app_default_hostname" {
  value = azurerm_linux_function_app.func.default_hostname
}

output "eventhub_connection_string" {
  value     = azurerm_eventhub_authorization_rule.eh_rule.primary_connection_string
  sensitive = true
}

output "cosmos_db_endpoint" {
  value = azurerm_cosmosdb_account.cosmos.endpoint
}

output "storage_account_name" {
  value = azurerm_storage_account.sa.name
}

output "function_app_principal_id" {
  value = azurerm_linux_function_app.func.identity[0].principal_id
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
