import unittest
from unittest.mock import patch, MagicMock
from budget_manager import CustomBudgetManager
from budget_utils import ModelPricing
import logging
import os
import json
from datetime import datetime, timedelta

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more verbose output
    format='%(message)s',  # Simplified format for cleaner output
    force=True  # Force reconfiguration
)

class TestBudgetManager(unittest.TestCase):
    def setUp(self):
        # Mock Cosmos DB container
        self.mock_container = MagicMock()
        self.mock_container.query_items.return_value = []
        self.mock_container.upsert_item.side_effect = lambda x: x

        # Create patcher for CosmosClient
        self.cosmos_patcher = patch('budget_manager.CosmosClient')
        self.mock_cosmos_client = self.cosmos_patcher.start()
        
        # Mock ModelPricing with different costs for different models
        self.model_pricing_patcher = patch('budget_utils.ModelPricing')
        self.mock_model_pricing = self.model_pricing_patcher.start()
        mock_pricing_instance = MagicMock()
        
        def get_model_cost(model, input_tokens, output_tokens):
            costs = {
                "gpt-4": (0.00003, 0.00006),  # (input cost, output cost) per token
                "gpt-4o": (0.000015, 0.000075)  # GPT-4-Opus costs
            }
            model_costs = costs.get(model, (0.00001, 0.00002))
            return (input_tokens * model_costs[0]) + (output_tokens * model_costs[1])
            
        mock_pricing_instance.get_model_cost.side_effect = get_model_cost
        self.mock_model_pricing.return_value = mock_pricing_instance
        
        # Setup mock database and container
        mock_database = MagicMock()
        mock_database.get_container_client.return_value = self.mock_container
        self.mock_cosmos_client.return_value.get_database_client.return_value = mock_database

        # Initialize budget manager
        self.budget_manager = CustomBudgetManager()
        
        # Test user details
        self.user_id_1 = "test_user_1"
        self.user_id_2 = "test_user_2"
        self.total_budget_1 = 100.0
        self.total_budget_2 = 50.0

        logging.info("\n=== Starting New Test ===")

    def tearDown(self):
        self.cosmos_patcher.stop()
        self.model_pricing_patcher.stop()

    def test_has_budget_non_existent(self):
        """Test checking non-existent budget"""
        has_budget = self.budget_manager.has_budget(self.user_id_1)
        self.assertFalse(has_budget)
        logging.info(f"Test has_budget_non_existent passed")

    def test_setup_user_budget(self):
        """Test setting up budget for first time"""
        self.budget_manager.setup_user_budget(
            user_id=self.user_id_1,
            total_budget=self.total_budget_1,
            duration='daily'
        )
        
        # Verify budget was created
        has_budget = self.budget_manager.has_budget(self.user_id_1)
        self.assertTrue(has_budget)
        
        # Verify budget details
        user_data = self.budget_manager.user_dict["users"][self.user_id_1]
        self.assertEqual(user_data["total_budget"], self.total_budget_1)
        self.assertEqual(user_data["duration"], "daily")
        self.assertEqual(user_data["current_cost"], 0.0)
        logging.info(f"Test setup_user_budget passed")

    def test_track_request_cost(self):
        """Test tracking cost for a request"""
        # Setup user budget first
        self.budget_manager.setup_user_budget(
            user_id=self.user_id_1,
            total_budget=self.total_budget_1,
            duration='daily'
        )
        
        # Test tracking cost
        model = "gpt-4"
        input_text = "Hello, how are you?"
        output_text = "I'm doing well, thank you for asking!"
        
        new_cost = self.budget_manager.track_request_cost(
            user_id=self.user_id_1,
            model=model,
            input_text=input_text,
            output_text=output_text
        )
        
        # Verify cost was tracked
        self.assertGreater(new_cost, 0)
        self.assertEqual(new_cost, self.budget_manager.get_user_cost(self.user_id_1))
        logging.info(f"Test track_request_cost passed")

    def test_budget_reset(self):
        """Test budget reset functionality"""
        # Setup user budget
        self.budget_manager.setup_user_budget(
            user_id=self.user_id_1,
            total_budget=self.total_budget_1,
            duration='daily'
        )
        
        # Add some cost
        model = "gpt-4"
        input_text = "Test message"
        output_text = "Test response"
        
        initial_cost = self.budget_manager.track_request_cost(
            user_id=self.user_id_1,
            model=model,
            input_text=input_text,
            output_text=output_text
        )
        
        # Set last_reset to yesterday
        user_data = self.budget_manager.user_dict["users"][self.user_id_1]
        yesterday = datetime.utcnow() - timedelta(days=1, hours=1)
        user_data["last_reset"] = yesterday.isoformat()
        
        # Track new cost which should trigger reset
        new_cost = self.budget_manager.track_request_cost(
            user_id=self.user_id_1,
            model=model,
            input_text=input_text,
            output_text=output_text
        )
        
        # Verify budget was reset
        self.assertEqual(new_cost, 0.01)  # Only the new cost after reset
        self.assertEqual(new_cost, self.budget_manager.get_user_cost(self.user_id_1))
        logging.info(f"Test budget_reset passed")

    def test_track_request_cost_multiple_models(self):
        """Test tracking cost for different models"""
        # Setup user budget
        self.budget_manager.setup_user_budget(
            user_id=self.user_id_1,
            total_budget=self.total_budget_1,
            duration='daily'
        )
        logging.info(f"\n{'='*80}\nBudget Test Results\n{'='*80}")
        logging.info(f"Initial budget setup for {self.user_id_1}: ${self.total_budget_1:.2f}")
        
        # Test cases for different models and message lengths
        test_cases = [
            {
                "model": "gpt-4",
                "input": "Hello, how are you? This is a longer input to test token counting with GPT-4. We need more tokens to see a meaningful cost difference.",
                "output": "I'm doing well! Thanks for asking. Here's a detailed response to test output tokens with GPT-4. Adding more text to make the cost calculation more interesting.",
                "description": "GPT-4 with medium length message"
            },
            {
                "model": "gpt-4o",
                "input": "What's the weather like today? Adding more text for token testing with GPT-4-Opus. We need a good number of tokens to see the cost difference.",
                "output": "The weather is sunny! Adding more text to test output token costs with GPT-4-Opus. Making this response longer to see the cost implications.",
                "description": "GPT-4-Opus with medium length message"
            }
        ]
        
        for case in test_cases:
            logging.info(f"\n{'-'*80}")
            logging.info(f"Testing Model: {case['model']}")
            logging.info(f"{'-'*80}")
            logging.info(f"Input text ({len(case['input'].split())} tokens):\n{case['input']}")
            logging.info(f"Output text ({len(case['output'].split())} tokens):\n{case['output']}")
            
            # Calculate token counts (simple approximation)
            input_tokens = len(case['input'].split())
            output_tokens = len(case['output'].split())
            
            # Track cost
            new_cost = self.budget_manager.track_request_cost(
                user_id=self.user_id_1,
                model=case['model'],
                input_text=case['input'],
                output_text=case['output']
            )
            
            current_total = self.budget_manager.get_user_cost(self.user_id_1)
            
            # Cost breakdown
            if case['model'] == "gpt-4":
                input_cost = input_tokens * 0.00003
                output_cost = output_tokens * 0.00006
            else:  # gpt-4o
                input_cost = input_tokens * 0.000015
                output_cost = output_tokens * 0.000075
                
            logging.info(f"\nCost Breakdown:")
            logging.info(f"Input cost (${input_cost:.6f}): {input_tokens} tokens × ${input_cost/input_tokens:.6f}/token")
            logging.info(f"Output cost (${output_cost:.6f}): {output_tokens} tokens × ${output_cost/output_tokens:.6f}/token")
            logging.info(f"Total request cost: ${new_cost:.6f}")
            logging.info(f"Cumulative total cost: ${current_total:.6f}")
            
            # Get model-specific costs
            user_data = self.budget_manager.user_dict["users"][self.user_id_1]
            model_costs = user_data["model_cost"]
            logging.info(f"\nCost tracking by model:")
            for model, cost in model_costs.items():
                logging.info(f"{model}: ${cost:.6f}")

if __name__ == "__main__":
    unittest.main()
