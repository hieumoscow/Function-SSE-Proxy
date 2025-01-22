from re import I
import azure.functions as func
import logging
import json
from azurefunctions.extensions.http.fastapi import Request
from fastapi.responses import JSONResponse

# Configure logger
logger = logging.getLogger('azure.func.budget')

blueprint = func.Blueprint()

# Constants
DEFAULT_BUDGET = 1e9  # 1 billion - effectively unlimited but JSON serializable

# Cosmos DB connection settings
cosmos_output_args = {"connection": "CosmosDBConnection"}

@blueprint.function_name(name="get_budget")
@blueprint.route(route="get_budget", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@blueprint.cosmos_db_input(
    arg_name="budgetDocuments",
    database_name="ApimAOAI",
    container_name="UserBudgets",
    id="{project_name}",
    **cosmos_output_args
)
async def get_budget(req: Request, budgetDocuments: func.DocumentList) -> JSONResponse:
    try:
        req_body = await req.json()
        logger.info(f"Get budget request received with body: {json.dumps(req_body)}")
        
        project_name = req_body.get('project_name')
        if not project_name:
            error_msg = "project_name is required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        if not budgetDocuments:
            logger.info(f"No budget found for project {project_name}, returning default budget")
            default_budget = {
                "id": project_name,
                "project_name": project_name,
                "total_budget": DEFAULT_BUDGET,
                "duration": "daily",
                "current_cost": 0.0,
                "model_cost": {},
                "status": "active"
            }
            return JSONResponse(content={"status": "success", "data": default_budget})
            
        logger.info(f"Found existing budget for project {project_name}")
        for budget in budgetDocuments:
            logger.info(f"Budget found: {budget.to_dict()}")
        budget_dict = budgetDocuments[0].to_dict()
        return JSONResponse(content={"status": "success", "data": budget_dict})
        
    except Exception as e:
        error_msg = f"Error in get_budget: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(content={"status": "error", "message": error_msg}, status_code=500)

@blueprint.function_name(name="set_budget")
@blueprint.route(route="set_budget", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@blueprint.cosmos_db_output(
    arg_name="outputDocument",
    database_name="ApimAOAI",
    container_name="UserBudgets",
    **cosmos_output_args
)
async def set_budget(req: Request, outputDocument: func.Out[func.Document]) -> JSONResponse:
    try:
        budget_data = await req.json()
        logger.info(f"Set budget request received with data: {json.dumps(budget_data)}")
        
        project_name = budget_data.get('project_name')
        if not project_name:
            error_msg = "project_name is required"
            logger.error(error_msg)
            return JSONResponse(content={"status": "error", "message": error_msg}, status_code=400)
        
        # Ensure id matches project_name
        budget_data['id'] = project_name
        budget_data['status'] = 'active'
        
        logger.info(f"Setting budget for project {project_name}")
        outputDocument.set(func.Document.from_dict(budget_data))
        return JSONResponse(content={"status": "success", "data": budget_data})
        
    except Exception as e:
        error_msg = f"Error in set_budget: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(content={"status": "error", "message": error_msg}, status_code=500)
