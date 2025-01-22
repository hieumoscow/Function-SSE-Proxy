from budget_manager import CustomBudgetManager
import logging
import os
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_budget_manager():
    # Initialize budget manager
    budget_manager = CustomBudgetManager()
    
    # Test user details
    user_id_1 = "test_user_1"
    user_id_2 = "test_user_2"
    total_budget_1 = 100.0
    total_budget_2 = 50.0
    
    try:
        # Log initial state
        budget_manager_instance = budget_manager.get_budget_manager()
        logging.info(f"Initial budget manager state: {budget_manager_instance.user_dict}")
        
        # Test checking non-existent budget
        logging.info(f"\n=== Testing has_budget ===")
        logging.info(f"Input - user_id: {user_id_1}")
        has_budget = budget_manager.has_budget(user_id_1)
        logging.info(f"Output - has_budget: {has_budget}")
        
        # Test setting up budget for first time
        logging.info(f"\n=== Testing setup_user_budget ===")
        logging.info(f"Input - user_id: {user_id_1}, total_budget: {total_budget_1}, duration: daily")
        budget_manager.setup_user_budget(
            user_id=user_id_1,
            total_budget=total_budget_1,
            duration='daily'
        )
        logging.info(f"Budget manager state after setup: {budget_manager_instance.user_dict}")
        
        # Test checking existing budget
        logging.info(f"\n=== Testing has_budget after setup ===")
        logging.info(f"Input - user_id: {user_id_1}")
        has_budget = budget_manager.has_budget(user_id_1)
        logging.info(f"Output - has_budget: {has_budget}")
        
        # Test attempting to set up budget again for same user
        logging.info(f"\n=== Testing setup_user_budget again ===")
        logging.info(f"Input - user_id: {user_id_1}, total_budget: {total_budget_1}, duration: daily")
        budget_manager.setup_user_budget(
            user_id=user_id_1,
            total_budget=total_budget_1,
            duration='daily'
        )
        
        # Test setting up budget for second user
        logging.info(f"\n=== Testing setup_user_budget for second user ===")
        logging.info(f"Input - user_id: {user_id_2}, total_budget: {total_budget_2}, duration: daily")
        budget_manager.setup_user_budget(
            user_id=user_id_2,
            total_budget=total_budget_2,
            duration='daily'
        )
        
        # Test getting costs
        logging.info(f"\n=== Testing get_user_cost ===")
        logging.info(f"Input - user_id: {user_id_1}")
        current_cost_1 = budget_manager.get_user_cost(user_id=user_id_1)
        logging.info(f"Output - current_cost: {current_cost_1}")
        
        logging.info(f"\n=== Testing get_user_cost for second user ===")
        logging.info(f"Input - user_id: {user_id_2}")
        current_cost_2 = budget_manager.get_user_cost(user_id=user_id_2)
        logging.info(f"Output - current_cost: {current_cost_2}")
        
        # Test tracking cost
        logging.info(f"\n=== Testing track_request_cost ===")
        model = "gpt-4-0613"
        input_text = "Hello, how are you?"
        output_text = "I'm doing well, thank you for asking!"
        
        logging.info(f"Input parameters:")
        logging.info(f"  user_id: {user_id_1}")
        logging.info(f"  model: {model}")
        logging.info(f"  input_text: {input_text}")
        logging.info(f"  output_text: {output_text}")
        
        try:
            new_cost = budget_manager.track_request_cost(
                user_id=user_id_1,
                model=model,
                input_text=input_text,
                output_text=output_text
            )
            logging.info(f"Output - new_cost: {new_cost}")
            logging.info(f"Budget manager state after cost tracking: {budget_manager_instance.user_dict}")
        except Exception as e:
            logging.error(f"Error tracking cost: {e}")
            raise
        
    except Exception as e:
        logging.error(f"Error during test: {e}")
        raise

if __name__ == "__main__":
    # Configure logging with more detailed format
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Set environment variables if needed
    os.environ['FUNCTION_APP_URL'] = 'http://localhost:7071/api'
    
    # Run tests
    test_budget_manager()
