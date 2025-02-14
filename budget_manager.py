import logging
import os
from typing import Optional, Dict, Any
import json
from datetime import datetime, timedelta
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

class CustomBudgetManager:
    def __init__(self):
        self.user_dict = {}
        self.project_name = "apim-aoai-budget"
        self.database_name = "ApimAOAI"
        self.container_name = "UserBudgets"
        self._setup_cosmos_client()
        self.load_data()

    def _setup_cosmos_client(self):
        """Setup Azure Cosmos DB client"""
        try:
            # Try getting connection string first (local development)
            connection_info = os.environ.get("CosmosDBConnection__accountEndpoint")
            key = os.environ.get("CosmosDBConnection__accountKey")
            
            if connection_info and key:
                # Local development with connection string
                self.cosmos_client = CosmosClient(connection_info, credential=key)
            else:
                # Production environment using managed identity
                endpoint = os.environ.get("CosmosDBConnection__accountEndpoint")
                if not endpoint:
                    raise ValueError("No Cosmos DB endpoint configured")
                    
                credential = DefaultAzureCredential()
                self.cosmos_client = CosmosClient(endpoint, credential=credential)
            
            # Get database
            self.database = self.cosmos_client.get_database_client(self.database_name)
            # Get container
            self.container = self.database.get_container_client(self.container_name)
            
        except Exception as e:
            logging.error(f"Error setting up Cosmos DB client: {str(e)}")
            raise

    def load_data(self) -> None:
        """Load budget data from Cosmos DB"""
        try:
            query = f"SELECT * FROM c WHERE c.id = '{self.project_name}'"
            items = list(self.container.query_items(query=query, enable_cross_partition_query=True))
            if items:
                self.user_dict = items[0]
            else:
                # Initialize with default data
                self.user_dict = {
                    "id": self.project_name,
                    "project_name": self.project_name
                }
                self.container.upsert_item(self.user_dict)
        except Exception as e:
            logging.error(f"Error loading budget data: {e}")

    def save_data(self) -> None:
        """Save budget data to Cosmos DB"""
        try:
            self.container.upsert_item(self.user_dict)
        except Exception as e:
            logging.error(f"Error saving budget data: {e}")

    def has_budget(self, user_id: str) -> bool:
        """
        Check if a user has an existing budget
        
        Args:
            user_id (str): Unique identifier for the user
            
        Returns:
            bool: True if user has budget, False otherwise
        """
        try:
            return user_id in self.user_dict.get("users", {})
        except Exception as e:
            logging.error(f"Error checking budget for user {user_id}: {e}")
            return False

    def setup_user_budget(self, user_id: str, total_budget: float, duration: str = "daily") -> None:
        """
        Setup budget for a user if it doesn't exist
        
        Args:
            user_id (str): Unique identifier for the user
            total_budget (float): Total budget amount
            duration (str): Budget duration ('daily', 'weekly', 'monthly')
        """
        try:
            if self.has_budget(user_id):
                logging.info(f"Budget already exists for user {user_id}")
                return
                
            logging.info(f"Setting up budget for user {user_id}: {total_budget} {duration}")
            if "users" not in self.user_dict:
                self.user_dict["users"] = {}
            self.user_dict["users"][user_id] = {
                "total_budget": total_budget,
                "duration": duration,
                "current_cost": 0.0,
                "model_cost": {},
                "last_reset": datetime.utcnow().isoformat()
            }
            self.save_data()
            logging.info(f"Budget setup successful for user {user_id}")
        except Exception as e:
            logging.error(f"Error setting up budget for user {user_id}: {e}")
            raise

    def track_request_cost(
        self,
        user_id: str,
        model: str,
        input_text: str,
        output_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Track the cost of an API request
        
        Args:
            user_id (str): Unique identifier for the user
            model (str): The model used for the request
            input_text (str): Input prompt text
            output_text (str): Generated output text
            metadata (Optional[Dict[str, Any]]): Additional metadata for tracking
            
        Returns:
            float: Current cost for the user
        """
        try:
            if not self.has_budget(user_id):
                raise ValueError(f"No budget found for user {user_id}")

            # Calculate cost using model_prices.json
            from budget_utils import ModelPricing
            pricing = ModelPricing()
            
            # Estimate tokens (this is a simple approximation)
            input_tokens = len(input_text.split())
            output_tokens = len(output_text.split())
            
            cost = pricing.get_model_cost(model, input_tokens, output_tokens)
            
            user_data = self.user_dict["users"][user_id]
            
            # Reset budget if needed based on duration
            self._check_and_reset_budget(user_id)
            
            # Update costs
            user_data["current_cost"] = user_data.get("current_cost", 0) + cost
            if model not in user_data["model_cost"]:
                user_data["model_cost"][model] = 0
            user_data["model_cost"][model] += cost
            
            self.save_data()
            return user_data["current_cost"]
            
        except Exception as e:
            logging.error(f"Error tracking cost for user {user_id}: {e}")
            raise

    def _check_and_reset_budget(self, user_id: str) -> None:
        """Reset budget if the duration has passed"""
        user_data = self.user_dict["users"][user_id]
        last_reset = datetime.fromisoformat(user_data.get("last_reset", datetime.min.isoformat()))
        now = datetime.utcnow()
        
        duration = user_data.get("duration", "daily")
        should_reset = False
        
        if duration == "daily" and (now - last_reset).days >= 1:
            should_reset = True
        elif duration == "weekly" and (now - last_reset).days >= 7:
            should_reset = True
        elif duration == "monthly" and (now - last_reset).days >= 30:
            should_reset = True
            
        if should_reset:
            user_data["current_cost"] = 0.0
            user_data["model_cost"] = {}
            user_data["last_reset"] = now.isoformat()

    def get_user_cost(self, user_id: str) -> float:
        """
        Get current cost for a user
        
        Args:
            user_id (str): Unique identifier for the user
            
        Returns:
            float: Current cost for the user
        """
        try:
            if not self.has_budget(user_id):
                return 0.0
            
            user_data = self.user_dict["users"][user_id]
            return user_data.get("current_cost", 0.0)
        except Exception as e:
            logging.error(f"Error getting cost for user {user_id}: {e}")
            raise