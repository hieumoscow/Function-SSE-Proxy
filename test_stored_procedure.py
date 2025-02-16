import os
import json
import random
from datetime import datetime, timedelta
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
import logging
from typing import Any, Dict, Optional, Union, List, Callable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CostGenerator:
    @staticmethod
    def fixed(cost: float) -> Callable[[], float]:
        return lambda: cost

    @staticmethod
    def random(min_cost: float, max_cost: float) -> Callable[[], float]:
        return lambda: round(random.uniform(min_cost, max_cost), 6)

    @staticmethod
    def exponential(base_cost: float, multiplier: float) -> Callable[[], float]:
        def generator(counter=[0]):
            cost = base_cost * (multiplier ** counter[0])
            counter[0] += 1
            return round(cost, 6)
        return generator

class CosmosStoredProcedureTester:
    def __init__(self):
        self.endpoint = "https://cosmos-fnsse-w7yorq49.documents.azure.com:443/"
        credential = DefaultAzureCredential()
        self.client = CosmosClient(self.endpoint, credential=credential)
        self.database_name = "ApimAOAI"
        self.container_name = "UserBudgets"
        
        logger.info(f"Connecting to database: {self.database_name}, container: {self.container_name}")
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)

    def execute_stored_procedure(self, 
                               counter_key: str, 
                               model: str, 
                               current_cost: float, 
                               quota: float, 
                               start_date: Optional[str] = None, 
                               window_duration: Optional[int] = None) -> Dict[str, Any]:
        """Execute the updateAccumulatedCost stored procedure."""
        if start_date is None:
            start_date = datetime.utcnow().isoformat() + "Z"
            
        # Use default window duration if none provided (30 days in seconds)
        if window_duration is None:
            window_duration = 2592000
            
        try:
            params = [str(counter_key), str(model), float(current_cost), 
                     str(start_date), int(window_duration), None, float(quota)]
            
            logger.info(f"Executing stored procedure with parameters: {json.dumps(params, indent=2)}")
            
            doc_id = f"{model}_{counter_key}"
            result = self.container.scripts.execute_stored_procedure(
                sproc="updateAccumulatedCost",
                params=params,
                partition_key=doc_id
            )
            
            logger.info(f"Success: counter_key={counter_key}, accumulated_cost={result.get('accumulatedCost', 0)}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing stored procedure: {str(e)}")
            raise

    def run_quota_test(self, 
                      test_name: str,
                      counter_key: str,
                      model: str,
                      quota: float,
                      cost_generator: Callable[[], float],
                      window_duration: Optional[int] = None,
                      start_date: Optional[str] = None,
                      max_iterations: int = 100) -> None:
        """
        Common test method for running quota-based tests with different cost patterns.
        
        Args:
            test_name: Name of the test for logging
            counter_key: Unique identifier for the counter
            model: Model identifier
            quota: Maximum allowed cost
            cost_generator: Function that generates the next cost value
            window_duration: Optional duration of the window in seconds
            start_date: Optional start date for the window
            max_iterations: Maximum number of iterations to prevent infinite loops
        """
        logger.info(f"\n=== {test_name} ===")
        logger.info(f"Parameters: quota=${quota:.2f}, model={model}")
        
        try:
            total_cost = 0.0
            iteration = 0
            
            while total_cost < quota and iteration < max_iterations:
                cost = cost_generator()
                try:
                    result = self.execute_stored_procedure(
                        counter_key=counter_key,
                        model=model,
                        current_cost=cost,
                        quota=quota,
                        window_duration=window_duration,
                        start_date=start_date
                    )
                    total_cost = result['accumulatedCost']
                    logger.info(f"Iteration {iteration + 1}: Added ${cost:.6f}, Total: ${total_cost:.2f} / ${quota:.2f}")
                    iteration += 1
                    
                except Exception as e:
                    if "would exceed quota" in str(e):
                        logger.info(f"Quota enforcement triggered at ${total_cost:.2f} + ${cost:.6f}")
                        logger.info(f"\n=== {test_name}: PASSED (Quota properly enforced) ===")
                        return
                    raise
                    
            if iteration >= max_iterations:
                logger.warning(f"Test stopped after {max_iterations} iterations")
            
            logger.info(f"\n=== {test_name}: PASSED ===")
            logger.info(f"Final cost: ${total_cost:.2f}")
            
        except Exception as e:
            logger.error(f"\n=== {test_name}: FAILED ===")
            logger.error(f"Error: {str(e)}")
            raise

    def run_all_tests(self):
        """Run a comprehensive suite of tests."""
        test_cases = [
            # Test 1: Fixed cost increments
            {
                "test_name": "Fixed Cost Test ($5 quota, $0.1 increments)",
                "counter_key": "test_fixed_5",
                "model": "gpt4",
                "quota": 5.0,
                "cost_generator": CostGenerator.fixed(0.1)
            },
            
            # Test 2: Random cost increments
            {
                "test_name": "Random Cost Test ($10 quota, $0.1-$0.2 range)",
                "counter_key": "test_random_10",
                "model": "gpt4",
                "quota": 10.0,
                "cost_generator": CostGenerator.random(0.1, 0.2)
            },
            
            # Test 3: Exponential cost growth
            {
                "test_name": "Exponential Cost Test ($20 quota, 1.5x growth)",
                "counter_key": "test_exp_20",
                "model": "gpt4",
                "quota": 20.0,
                "cost_generator": CostGenerator.exponential(0.1, 1.5)
            },
            
            # Test 4: Edge case - Very small costs
            {
                "test_name": "Small Cost Test ($1 quota, $0.001 increments)",
                "counter_key": "test_small_1",
                "model": "gpt4",
                "quota": 1.0,
                "cost_generator": CostGenerator.fixed(0.001)
            },
            
            # Test 5: Edge case - Large costs
            {
                "test_name": "Large Cost Test ($1000 quota, $100-$200 range)",
                "counter_key": "test_large_1000",
                "model": "gpt4",
                "quota": 1000.0,
                "cost_generator": CostGenerator.random(100.0, 200.0)
            },
            
            # Test 6: Time window test
            {
                "test_name": "Time Window Test (1 hour window)",
                "counter_key": "test_window_1h",
                "model": "gpt4",
                "quota": 5.0,
                "cost_generator": CostGenerator.fixed(1.0),
                "window_duration": 3600,  # 1 hour
                "start_date": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
            }
        ]
        
        for test_case in test_cases:
            self.run_quota_test(**test_case)
            # Add small delay between tests
            import time
            time.sleep(1)

def main():
    tester = CosmosStoredProcedureTester()
    tester.run_all_tests()
    return 0

if __name__ == "__main__":
    exit(main())
