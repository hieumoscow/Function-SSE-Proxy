from litellm import BudgetManager
import logging
import os
from typing import Optional, Dict, Any

class CustomBudgetManager:
    _budget_manager = None

    def get_budget_manager(self, project_name: str = None) -> BudgetManager:
        """Get or create a budget manager instance"""
        if self._budget_manager is None or project_name:
            function_app_url = os.getenv('FUNCTION_APP_URL', 'http://localhost:7071/api')
            self._budget_manager = BudgetManager(
                project_name=project_name or "apim-aoai-budget",
                client_type="hosted",
                api_base=function_app_url
            )
            # Load existing data once when creating
            self._budget_manager.load_data()
        return self._budget_manager

    def has_budget(self, user_id: str) -> bool:
        """
        Check if a user has an existing budget
        
        Args:
            user_id (str): Unique identifier for the user
            
        Returns:
            bool: True if user has budget, False otherwise
        """
        try:
            budget_manager = self.get_budget_manager()
            return user_id in budget_manager.user_dict
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
            budget_manager = self.get_budget_manager()
            budget_manager.create_budget(
                user=user_id,
                total_budget=total_budget,
                duration=duration
            )
            # Initialize cost fields if not present
            if user_id in budget_manager.user_dict and "current_cost" not in budget_manager.user_dict[user_id]:
                budget_manager.user_dict[user_id].update({
                    "current_cost": 0.0,
                    "model_cost": {}
                })
            # Save the data after creating budget
            budget_manager.save_data()
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
            budget_manager = self.get_budget_manager()
            
            budget_manager.update_cost(
                user=user_id,
                model=model,
                input_text=input_text,
                output_text=output_text,
            )

            # Save after updating cost
            budget_manager.save_data()
            
            current_cost = budget_manager.user_dict[user_id]["current_cost"]
            logging.info(f"Cost tracked successfully for user {user_id}. Model: {model}. Current cost: {current_cost}")
            return current_cost
        except Exception as e:
            logging.error(f"Error tracking cost for user {user_id}: {e}")
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
            budget_manager = self.get_budget_manager()
            if not self.has_budget(user_id):
                return 0.0
            
            user_data = budget_manager.user_dict[user_id]
            return user_data.get("current_cost", 0.0)
        except Exception as e:
            logging.error(f"Error getting cost for user {user_id}: {e}")
            raise