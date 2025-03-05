import json
import os
import logging
from typing import Dict, Any
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# Global variables
_cosmos_client = None
_model_pricing = None

class ModelPricing:
    def __init__(self):
        self.model_prices = self._load_model_prices()
    
    def _load_model_prices(self) -> Dict[str, Any]:
        """Load model prices from the JSON file"""
        json_path = os.path.join(os.path.dirname(__file__), 'model_prices_and_context_window.json')
        with open(json_path, 'r') as f:
            return json.load(f)
    
    def get_model_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a model based on input and output tokens"""
        if model not in self.model_prices:
            # Default to a safe minimal cost if model not found
            return (input_tokens + output_tokens) * 0.0001
            
        model_info = self.model_prices[model]
        input_cost = model_info.get('input_cost_per_token', 0) * input_tokens
        output_cost = model_info.get('output_cost_per_token', 0) * output_tokens
        
        return input_cost + output_cost

    def get_token_limits(self, model: str) -> tuple:
        """Get input and output token limits for a model"""
        if model not in self.model_prices:
            # Default safe limits
            return (4096, 4096)
            
        model_info = self.model_prices[model]
        input_limit = model_info.get('max_input_tokens', 4096)
        output_limit = model_info.get('max_output_tokens', 4096)
        
        return (input_limit, output_limit)

def get_model_pricing():
    """
    Get or initialize the model pricing object
    
    Returns:
        ModelPricing: Model pricing object
    """
    global _model_pricing
    if _model_pricing is None:
        _model_pricing = ModelPricing()
    return _model_pricing

def get_cosmos_client():
    """
    Get or initialize the Cosmos DB client
    
    Returns:
        CosmosClient: Cosmos DB client
    """
    global _cosmos_client
    if _cosmos_client is None:
        try:
            # Try getting connection string first (local development)
            connection_info = os.environ.get("CosmosDBConnection__accountEndpoint")
            key = os.environ.get("CosmosDBConnection__accountKey")
            
            if connection_info and key:
                # Local development with connection string
                _cosmos_client = CosmosClient(connection_info, credential=key)
            else:
                # Production environment using managed identity
                endpoint = os.environ.get("CosmosDBConnection__accountEndpoint")
                if not endpoint:
                    raise ValueError("No Cosmos DB endpoint configured")
                    
                credential = DefaultAzureCredential()
                _cosmos_client = CosmosClient(endpoint, credential=credential)
            
            logging.info("Created Cosmos DB client")
        except Exception as e:
            logging.error(f"Error setting up Cosmos DB client: {str(e)}")
            raise
    return _cosmos_client

def check_quota_exceeded(rate_limit_config):
    """
    Check if the quota is exceeded for the given counter key
    
    Args:
        rate_limit_config (dict): Configuration for rate limiting
        
    Returns:
        dict: None if document doesn't exist or error, dict with quota exceeded info if quota exceeded,
             or dict with document info (accumulated_cost, quota, counter_key) if quota not exceeded
    """
    try:
        if not rate_limit_config:
            logging.info("No rate limit config provided, skipping quota check")
            return None
            
        counter_key = rate_limit_config.get("counterKey")
        if not counter_key:
            logging.warning("No counterKey provided in rateLimitConfig, skipping quota check")
            return None
            
        quota = rate_limit_config.get("quota")
        if not quota:
            logging.warning("No quota provided in rateLimitConfig, skipping quota check")
            return None
            
        # Get Cosmos DB client and container
        cosmos_client = get_cosmos_client()
        database = cosmos_client.get_database_client("ApimAOAI")
        container = database.get_container_client("UserBudgets")
        
        # Use just the counter_key to query documents
        logging.info(f"Checking quota for counter_key={counter_key}")
        
        try:
            # Try to read the document directly using counterKey as ID
            try:
                doc = container.read_item(item=counter_key, partition_key=counter_key)
                
                # Check if accumulated cost exceeds quota
                accumulated_cost = doc.get("accumulatedCost", 0)
                quota_value = doc.get("quota", float(quota))
                
                logging.info(f"Found document: counter_key={counter_key}, accumulated_cost={accumulated_cost}, quota={quota_value}")
                
                if accumulated_cost >= quota_value:
                    logging.warning(f"Quota exceeded for counter_key={counter_key}: accumulated_cost={accumulated_cost}, quota={quota_value}")
                    return {
                        "error": "QuotaExceeded",
                        "message": f"Rate limit quota exceeded. Accumulated cost: {accumulated_cost}, Quota: {quota_value}",
                        "status_code": 429,  # Too Many Requests
                        "accumulated_cost": accumulated_cost,
                        "quota": quota_value,
                        "counter_key": counter_key,
                        "quota_exceeded": True
                    }
                
                # Return document info even when quota is not exceeded
                return {
                    "accumulated_cost": accumulated_cost,
                    "quota": quota_value,
                    "counter_key": counter_key,
                    "quota_exceeded": False
                }
            except Exception as e:
                # Document might not exist yet, which is fine
                logging.info(f"Document not found or other error: {str(e)}")
                return None
        except Exception as e:
            # Error querying documents
            logging.error(f"Error querying documents: {str(e)}")
            return None
    except Exception as e:
        logging.error(f"Error checking quota: {str(e)}")
        return None

def track_cost_with_stored_procedure(rate_limit_config, model, current_cost):
    """
    Track cost using the Cosmos DB stored procedure
    
    Args:
        rate_limit_config (dict): Configuration for rate limiting
        model (str): Model name (used for logging only, not for document ID)
        current_cost (float): Cost of the current request
        
    Returns:
        dict: Result from the stored procedure or error information
    """
    try:
        if not rate_limit_config:
            logging.info("No rate limit config provided, skipping cost tracking")
            return None
        logging.info(f"model provided: {model}")
        logging.info(f"current_cost provided: {current_cost}")
        logging.info(f"Rate limit config provided: {json.dumps(rate_limit_config)}")
        counter_key = rate_limit_config.get("counterKey")
        if not counter_key:
            logging.warning("No counterKey provided in rateLimitConfig, skipping cost tracking")
            return None
            
        # Get required parameters
        start_date = rate_limit_config.get("startDate")
        renewal_period = rate_limit_config.get("renewal_period")
        explicit_end_date = rate_limit_config.get("explicitEndDate")
        quota = rate_limit_config.get("quota")
        
        if not quota:
            logging.warning("No quota provided in rateLimitConfig, skipping cost tracking")
            return None
            
        # Get Cosmos DB client and container
        cosmos_client = get_cosmos_client()
        database = cosmos_client.get_database_client("ApimAOAI")
        container = database.get_container_client("UserBudgets")
        
        # Log the parameters being sent to the stored procedure
        logging.info(f"Executing stored procedure with params: counter_key={counter_key}, " +
                    f"current_cost={current_cost}, start_date={start_date}, renewal_period={renewal_period}, " +
                    f"explicit_end_date={explicit_end_date}, quota={quota}, model={model} (for logging only)")
        
        # The stored procedure now uses counterKey as the document ID
        try:
            # Execute the stored procedure
            result = container.scripts.execute_stored_procedure(
                sproc="updateAccumulatedCost",
                params=[counter_key, current_cost, start_date, renewal_period, explicit_end_date, quota],
                partition_key=counter_key
            )
            
            logging.info(f"Stored procedure result: {result}")
            
            # Ensure we return a dictionary with the accumulated cost and quota
            if isinstance(result, dict):
                return result
            else:
                # If result is not a dictionary, try to create one with the expected structure
                try:
                    # Try to read the document to get the current accumulated cost and quota
                    doc = container.read_item(item=counter_key, partition_key=counter_key)
                    return {
                        "accumulatedCost": doc.get("accumulatedCost", 0),
                        "quota": doc.get("quota", float(quota)),
                        "counterKey": counter_key,
                        "result": result
                    }
                except Exception as e:
                    logging.error(f"Error reading document after stored procedure: {str(e)}")
                    return {
                        "accumulatedCost": 0,
                        "quota": float(quota),
                        "counterKey": counter_key,
                        "result": result
                    }
        except Exception as e:
            logging.error(f"Error executing stored procedure: {str(e)}")
            return {
                "error": str(e),
                "counterKey": counter_key,
                "accumulatedCost": 0,
                "quota": float(quota)
            }
    except Exception as e:
        logging.error(f"Error in track_cost_with_stored_procedure: {str(e)}")
        return {
            "error": str(e),
            "accumulatedCost": 0,
            "quota": 0
        }

def calculate_request_cost(model, input_text, output_text, rate_limit_config=None):
    """
    Calculate the cost of a request based on input and output tokens
    
    Args:
        model (str): Model name
        input_text (str): Input text
        output_text (str): Output text
        rate_limit_config (dict): Optional rate limit configuration
        
    Returns:
        float: Cost of the request
    """
    try:
        # Use custom token calculation if provided in rate_limit_config
        input_cost_per_token = None
        output_cost_per_token = None
        
        if rate_limit_config:
            input_cost_per_token = rate_limit_config.get("input_cost_per_token")
            output_cost_per_token = rate_limit_config.get("output_cost_per_token")
        
        # Estimate tokens (simple approximation)
        input_tokens = len(input_text.split())
        output_tokens = len(output_text.split())
        
        # Use model pricing from JSON file
        pricing = get_model_pricing()
        
        if input_cost_per_token is not None and output_cost_per_token is not None:
            # Use custom pricing from rate_limit_config
            cost = (input_cost_per_token * input_tokens) + (output_cost_per_token * output_tokens)
        else:
            # Use pricing from model_prices_and_context_window.json
            cost = pricing.get_model_cost(model, input_tokens, output_tokens)
            
        return cost
    except Exception as e:
        logging.error(f"Error calculating request cost: {str(e)}")
        return 0.0
