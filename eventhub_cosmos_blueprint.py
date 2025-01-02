# Register this blueprint by adding the following line of code 
# to your entry point file.  
# app.register_functions(blueprint) 
# 
# Please refer to https://aka.ms/azure-functions-python-blueprints

import logging
import json
import os
import azure.functions as func
import uuid
from azure.identity import DefaultAzureCredential


blueprint = func.Blueprint()



eventhub_trigger_args = {"connection": "EventHubConnection"}

cosmos_output_args = {"connection": "CosmosDBConnection"}

@blueprint.event_hub_message_trigger(
    arg_name="events", 
    event_hub_name=os.environ["AZURE_EVENTHUB_NAME"],
    **eventhub_trigger_args
) 
@blueprint.cosmos_db_output(
    arg_name="outputDocument",
    database_name="ApimAOAI",    
    container_name="ApimAOAI",
    **cosmos_output_args
)
def eventhub_trigger(events: func.EventHubEvent, outputDocument: func.Out[func.Document]):
    try:
        # Process the event
        event_body = events.get_body().decode('utf-8')
        event_data = json.loads(event_body)
        
        # Add new uuid as id if not exists
        if "id" not in event_data:
            event_data["id"] = str(uuid.uuid4())
        
        # Store in Cosmos DB using output binding
        outputDocument.set(func.Document.from_dict(event_data))
        
        logging.info(f"Successfully stored event in Cosmos DB: {event_data}")
        
    except Exception as e:
        logging.error(f"Error processing event: {str(e)}")
        raise
