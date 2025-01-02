#!/bin/bash

# Exit on error
set -e

echo "Starting function deployment process..."

# Get function app name from terraform output
FUNC_APP_NAME=$(terraform output -raw function_app_name)
RESOURCE_GROUP=$(terraform output -raw resource_group_name)

# Check if we got the outputs
if [ -z "$FUNC_APP_NAME" ] || [ -z "$RESOURCE_GROUP" ]; then
    echo "Error: Could not get required terraform outputs. Make sure terraform has been applied."
    exit 1
fi

echo "Deploying to Function App: $FUNC_APP_NAME"
cd ../
# Deploy the function code
func azure functionapp publish "$FUNC_APP_NAME" --python

echo "Function deployment completed successfully!"
