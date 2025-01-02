# Azure Function Infrastructure with MSI Authentication

This Terraform configuration deploys the following Azure resources:

- Azure Function App (Linux, Python 3.11)
- Azure Storage Account (for Function App)
- Azure Event Hub Namespace and Event Hub
- Azure Cosmos DB Account with SQL API
- Managed Service Identity (MSI) configurations

## Resources Created

- Resource Group
- Storage Account (for Function App)
- App Service Plan (Consumption)
- Linux Function App
- Event Hub Namespace
- Event Hub
- Event Hub Authorization Rule
- Cosmos DB Account
- Cosmos DB SQL Database
- Cosmos DB Container
- Role Assignments for MSI authentication

## Authentication

The Function App uses Managed Service Identity (MSI) for authentication:
- System-assigned identity is enabled on the Function App
- RBAC roles are assigned for Cosmos DB and Event Hub access
- No connection strings are needed in app settings (except for storage account)

## Usage

1. Initialize Terraform:
```bash
terraform init
```

2. Review the plan:
```bash
terraform plan
```

3. Apply the configuration:
```bash
terraform apply
```

4. After deployment, update your local.settings.json with the outputs:
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "<storage_account_connection_string>",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_EVENTHUB_NAME": "openai-logs",
    "AZURE_EVENTHUB_CONN_STR": "<eventhub_connection_string>",
    "CosmosDBConnection": "<cosmos_db_endpoint>"
  }
}
```

## Notes

- The OpenAI service is not included in this Terraform configuration and should be configured separately
- The Function App uses MSI authentication for Cosmos DB and Event Hub
- All resources are deployed in the East Asia region
- The Cosmos DB is configured with serverless capacity
