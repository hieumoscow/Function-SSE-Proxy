from litellm import BudgetManager
import logging
import json
from typing import Optional, Dict, Any

class CustomBudgetManager:
    def __init__(self):
        self.budget_manager = BudgetManager(project_name="azure_function_project")
        
    def setup_user_budget(self, user_id: str, total_budget: float, duration: str = "daily") -> None:
        """
        Setup budget for a user
        
        Args:
            user_id (str): Unique identifier for the user
            total_budget (float): Total budget amount
            duration (str): Budget duration ('daily', 'weekly', 'monthly')
        """
        try:
            self.budget_manager.create_budget(
                total_budget=total_budget,
                user=user_id,
                duration=duration
            )
            logging.info(f"Budget setup successful for user {user_id}")
        except Exception as e:
            logging.error(f"Error setting up budget for user {user_id}: {str(e)}")
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
            self.budget_manager.update_cost(
                user=user_id,
                model=model,
                input_text=input_text,
                output_text=output_text
            )
            
            current_cost = self.budget_manager.get_current_cost(user=user_id)
            logging.info(f"Cost tracked successfully for user {user_id}. Model: {model}. Current cost: {current_cost}")
            return current_cost
            
        except Exception as e:
            logging.error(f"Error tracking cost for user {user_id}: {str(e)}")
            raise

    def get_user_cost(self, user_id: str) -> float:
        """
        Get current cost for a user
        
        Args:
            user_id (str): Unique identifier for the user
            
        Returns:
            float: Current cost for the user
        """
        try:
            return self.budget_manager.get_current_cost(user=user_id)
        except Exception as e:
            logging.error(f"Error getting cost for user {user_id}: {str(e)}")
            raise