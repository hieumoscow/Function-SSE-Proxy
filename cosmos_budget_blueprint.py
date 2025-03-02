import azure.functions as func
import logging
import json
import os
from datetime import datetime
from azurefunctions.extensions.http.fastapi import Request
from fastapi.responses import JSONResponse
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from budget_utils import get_cosmos_client

# Configure logger
logger = logging.getLogger('azure.func.cosmos_budget')

blueprint = func.Blueprint()

@blueprint.function_name(name="get_cost_tracking")
@blueprint.route(route="get_cost_tracking", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def get_cost_tracking(req: Request) -> JSONResponse:
    """
    Get cost tracking information for a specific counter key and model
    """
    try:
        req_body = await req.json()
        logger.info(f"Get cost tracking request received with body: {json.dumps(req_body)}")
        
        counter_key = req_body.get('counterKey')
        model = req_body.get('model')
        
        if not counter_key or not model:
            error_msg = "counterKey and model are required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        # Get Cosmos DB client and container
        cosmos_client = get_cosmos_client()
        database = cosmos_client.get_database_client("ApimAOAI")
        container = database.get_container_client("UserBudgets")
        
        # Query for the document
        doc_id = f"{model}_{counter_key}"
        query = f"SELECT * FROM c WHERE c.id = '{doc_id}'"
        
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        
        if not items:
            logger.info(f"No cost tracking found for counter key {counter_key} and model {model}")
            return JSONResponse(content={"status": "success", "data": None})
        
        logger.info(f"Found cost tracking for counter key {counter_key} and model {model}")
        return JSONResponse(content={"status": "success", "data": items[0]})
        
    except Exception as e:
        error_msg = f"Error in get_cost_tracking: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(content={"status": "error", "message": error_msg}, status_code=500)

@blueprint.function_name(name="reset_cost_tracking")
@blueprint.route(route="reset_cost_tracking", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def reset_cost_tracking(req: Request) -> JSONResponse:
    """
    Reset cost tracking for a specific counter key and model
    """
    try:
        req_body = await req.json()
        logger.info(f"Reset cost tracking request received with body: {json.dumps(req_body)}")
        
        counter_key = req_body.get('counterKey')
        model = req_body.get('model')
        
        if not counter_key or not model:
            error_msg = "counterKey and model are required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        # Get Cosmos DB client and container
        cosmos_client = get_cosmos_client()
        database = cosmos_client.get_database_client("ApimAOAI")
        container = database.get_container_client("UserBudgets")
        
        # Query for the document
        doc_id = f"{model}_{counter_key}"
        query = f"SELECT * FROM c WHERE c.id = '{doc_id}'"
        
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        
        if not items:
            logger.info(f"No cost tracking found for counter key {counter_key} and model {model}")
            return JSONResponse(content={"status": "success", "message": "No cost tracking found to reset"})
        
        # Reset accumulated cost to 0
        doc = items[0]
        doc['accumulatedCost'] = 0
        doc['lastUpdated'] = datetime.utcnow().isoformat()
        
        # Update the document
        container.replace_item(item=doc['id'], body=doc)
        
        logger.info(f"Reset cost tracking for counter key {counter_key} and model {model}")
        return JSONResponse(content={"status": "success", "data": doc})
        
    except Exception as e:
        error_msg = f"Error in reset_cost_tracking: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(content={"status": "error", "message": error_msg}, status_code=500)

@blueprint.function_name(name="update_quota")
@blueprint.route(route="update_quota", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def update_quota(req: Request) -> JSONResponse:
    """
    Update quota for a specific counter key and model
    """
    try:
        req_body = await req.json()
        logger.info(f"Update quota request received with body: {json.dumps(req_body)}")
        
        counter_key = req_body.get('counterKey')
        model = req_body.get('model')
        quota = req_body.get('quota')
        
        if not counter_key or not model:
            error_msg = "counterKey and model are required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        if quota is None:
            error_msg = "quota is required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        # Get Cosmos DB client and container
        cosmos_client = get_cosmos_client()
        database = cosmos_client.get_database_client("ApimAOAI")
        container = database.get_container_client("UserBudgets")
        
        # Query for the document
        doc_id = f"{model}_{counter_key}"
        query = f"SELECT * FROM c WHERE c.id = '{doc_id}'"
        
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        
        if not items:
            logger.info(f"No cost tracking found for counter key {counter_key} and model {model}")
            return JSONResponse(content={"status": "success", "message": "No cost tracking found to update quota"})
        
        # Update quota
        doc = items[0]
        doc['quota'] = quota
        doc['lastUpdated'] = datetime.utcnow().isoformat()
        
        # Update the document
        container.replace_item(item=doc['id'], body=doc)
        
        logger.info(f"Updated quota for counter key {counter_key} and model {model} to {quota}")
        return JSONResponse(content={"status": "success", "data": doc})
        
    except Exception as e:
        error_msg = f"Error in update_quota: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(content={"status": "error", "message": error_msg}, status_code=500)
