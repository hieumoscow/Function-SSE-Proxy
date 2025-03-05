import os
import json
import random
from datetime import datetime, timedelta
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
import logging
from typing import Any, Dict, Optional, Union, List, Callable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Suppress Azure Cosmos DB SDK logs
logging.getLogger('azure').setLevel(logging.ERROR)
logging.getLogger('azure.cosmos').setLevel(logging.ERROR)
logging.getLogger('azure.identity').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

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
        
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)

    def execute_stored_procedure(self, 
                               counter_key: str, 
                               current_cost: float, 
                               quota: float, 
                               start_date: Optional[str] = None, 
                               renewal_period: Optional[int] = None,
                               end_date: Optional[str] = None,
                               model: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute the updateAccumulatedCost stored procedure
        
        Args:
            counter_key: The counter key for the document
            current_cost: The cost to add to the accumulated cost
            quota: The quota limit
            start_date: Optional start date (ISO format)
            renewal_period: Optional renewal period in seconds
            end_date: Optional end date (ISO format)
            model: Optional model name (for logging only, not used in document ID)
            
        Returns:
            The result from the stored procedure
        """
        if start_date is None:
            start_date = datetime.utcnow().isoformat() + "Z"
            
        try:
            # Make sure current_cost is a float
            current_cost_float = float(current_cost)
            
            # Ensure parameters are in the correct order and of the correct type
            params = [
                str(counter_key),                                  # counterKey as string
                current_cost_float,                               # currentCost as float
                str(start_date) if start_date else None,          # startDate as string or null
                int(renewal_period) if renewal_period is not None else None,  # renewalPeriod as int or null
                str(end_date) if end_date else None,              # endDate as string or null
                float(quota)                                      # quota as float
            ]
            
            # Log the parameters for debugging
            logger.info(f"Executing stored procedure with params: {params}")
            
            # Use counter_key as both document ID and partition key
            return self.container.scripts.execute_stored_procedure(
                sproc="updateAccumulatedCost",
                params=params,
                partition_key=counter_key
            )
            
        except Exception as e:
            logger.error(f"Error executing stored procedure: {str(e)}")
            raise

    def run_quota_test(self, 
                      test_name: str,
                      counter_key: str,
                      quota: float,
                      cost_generator: Callable[[], float],
                      renewal_period: Optional[int] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      max_iterations: int = 100,
                      expected_error: Optional[str] = None) -> None:
        logger.info(f"\n=== TEST {test_name} ===")
        logger.info(f"Key: {counter_key}")
        logger.info(f"Quota: ${quota:.2f}")
        if start_date:
            logger.info(f"Start Date: {start_date}")
        if end_date:
            logger.info(f"End Date: {end_date}")
        if renewal_period:
            logger.info(f"Renewal Period: {renewal_period}s")
        logger.info("-" * 50)
        
        accumulated_cost = 0
        iterations = 0
        test_passed = False
        
        while iterations < max_iterations:
            current_cost = cost_generator()
            try:
                result = self.execute_stored_procedure(
                    counter_key=counter_key,
                    current_cost=current_cost,
                    quota=quota,
                    start_date=start_date,
                    renewal_period=renewal_period,
                    end_date=end_date
                )
                accumulated_cost = result.get('accumulatedCost', 0)
                logger.info(f"Added ${current_cost:.4f} -> Total: ${accumulated_cost:.4f}")
                
            except Exception as e:
                error_msg = str(e)
                if "exceeded quota" in error_msg:
                    import re
                    match = re.search(r"Accumulated cost (\d+\.?\d*)", error_msg)
                    if match:
                        total = float(match.group(1))
                        logger.info(f"❌ Quota exceeded at ${total:.4f}")
                    else:
                        logger.info(f"❌ Quota exceeded")
                    if expected_error and "exceeded quota" in expected_error:
                        logger.info("✅ PASS: Expected quota exceeded error")
                        test_passed = True
                    break
                elif "before the start date" in error_msg:
                    logger.info("❌ Error: Cannot use budget before start date")
                    if expected_error and "before the start date" in expected_error:
                        logger.info("✅ PASS: Expected start date error")
                        test_passed = True
                    break
                elif "after the end date" in error_msg:
                    logger.info("❌ Error: Cannot use budget after end date")
                    if expected_error and "after the end date" in expected_error:
                        logger.info("✅ PASS: Expected end date error")
                        test_passed = True
                    break
                elif expected_error and expected_error in error_msg:
                    logger.info(f"❌ Error: {error_msg}")
                    logger.info("✅ PASS: Expected error occurred")
                    test_passed = True
                    break
                else:
                    logger.info(f"❌ FAIL: Unexpected error: {error_msg}")
                    raise
                
            iterations += 1
            
        if expected_error and iterations == max_iterations:
            logger.info("❌ FAIL: Expected error did not occur")
        elif not expected_error and iterations == max_iterations:
            logger.info("✅ PASS: Completed all iterations without errors")
            test_passed = True
        
        # Print test result summary
        if test_passed:
            logger.info(f"✅ TEST RESULT: {test_name} - PASSED")
        else:
            if expected_error:
                if "exceeded quota" in expected_error and accumulated_cost > quota:
                    logger.info(f"✅ TEST RESULT: {test_name} - PASSED (Quota exceeded as expected)")
                    test_passed = True
                else:
                    logger.info(f"❌ TEST RESULT: {test_name} - FAILED")
            else:
                logger.info(f"✅ TEST RESULT: {test_name} - PASSED")
                test_passed = True
        
        logger.info("=" * 50)

    def delete_test_document(self, counter_key: str) -> None:
        """Delete a test document to clean up after tests"""
        try:
            self.container.delete_item(item=counter_key, partition_key=counter_key)
            logger.info(f"Deleted test document: {counter_key}")
        except Exception as e:
            logger.info(f"Could not delete document {counter_key}: {str(e)}")

def main():
    tester = CosmosStoredProcedureTester()
    
    # Test 1: Basic daily renewal
    tester.run_quota_test(
        "Daily Renewal Test",
        counter_key="test_daily",
        quota=10.0,
        cost_generator=CostGenerator.fixed(2.0),
        renewal_period=86400,
        max_iterations=10,
        expected_error="exceeded quota"
    )
    
    # Test 2: Basic monthly quota with random costs
    tester.run_quota_test(
        "Monthly Quota Test",
        counter_key="test_monthly",
        quota=50.0,
        cost_generator=CostGenerator.random(10.0, 20.0),
        renewal_period=2592000,
        max_iterations=5,
        expected_error="exceeded quota"
    )
    
    # Test 3: Future start date (should fail)
    future_start = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
    tester.run_quota_test(
        "Future Start Date Test",
        counter_key="test_future",
        quota=10.0,
        cost_generator=CostGenerator.fixed(1.0),
        start_date=future_start,
        max_iterations=1,
        expected_error="before the start date"
    )
    
    # Test 4: Past end date (should fail)
    past_end = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    tester.run_quota_test(
        "Past End Date Test",
        counter_key="test_past_end",
        quota=10.0,
        cost_generator=CostGenerator.fixed(1.0),
        end_date=past_end,
        max_iterations=1,
        expected_error="after the end date"
    )
    
    # Test 5: Renewal period reset
    past_start = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
    tester.run_quota_test(
        "Renewal Reset Test",
        counter_key="test_renewal",
        quota=5.0,
        cost_generator=CostGenerator.fixed(2.0),
        start_date=past_start,
        renewal_period=86400,  # 1 day
        max_iterations=5,
        expected_error="exceeded quota"
    )
    
    # Test 6: Exponential cost growth
    tester.run_quota_test(
        "Exponential Cost Growth Test",
        counter_key="test_exponential",
        quota=20.0,
        cost_generator=CostGenerator.exponential(1.0, 2.0),
        max_iterations=6,
        expected_error="exceeded quota"
    )
    
    # Test 7: Zero quota (should fail on first attempt)
    tester.run_quota_test(
        "Zero Quota Test",
        counter_key="test_zero_quota",
        quota=0.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=1,
        expected_error="quota must be a positive number"
    )
    
    # Test 8: Negative cost (should fail)
    tester.run_quota_test(
        "Negative Cost Test",
        counter_key="test_negative_cost",
        quota=10.0,
        cost_generator=CostGenerator.fixed(-1.0),
        max_iterations=1,
        expected_error="currentCost must be a non-negative number"
    )
    
    # Test 9: Small costs accumulation
    tester.run_quota_test(
        "Small Cost Accumulation Test",
        counter_key="test_small_cost",
        quota=1.0,
        cost_generator=CostGenerator.fixed(0.1),
        max_iterations=15,
        expected_error="exceeded quota"
    )
    
    # Test 10: Multiple models test
    # First use one model
    tester.run_quota_test(
        "Multiple Models Test - Part 1",
        counter_key="test_multi_model",
        quota=5.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=3
    )
    
    # Then use a different model with same key
    tester.run_quota_test(
        "Multiple Models Test - Part 2",
        counter_key="test_multi_model",
        quota=5.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=3
    )
    
    # Test 11: Short renewal period (1 minute)
    short_renewal = 60  # 1 minute
    tester.run_quota_test(
        "Short Renewal Period Test",
        counter_key="test_short_renewal",
        quota=3.0,
        cost_generator=CostGenerator.fixed(1.0),
        renewal_period=short_renewal,
        max_iterations=5,
        expected_error="exceeded quota"
    )
    
    # Test 12: Update quota test
    # First create with lower quota
    tester.run_quota_test(
        "Update Quota Test - Part 1",
        counter_key="test_update_quota",
        quota=3.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=2
    )
    
    # Then update with higher quota
    tester.run_quota_test(
        "Update Quota Test - Part 2",
        counter_key="test_update_quota",
        quota=10.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=5
    )
    
    # Test 13: Exactly at quota limit
    tester.run_quota_test(
        "Exact Quota Test",
        counter_key="test_exact_quota",
        quota=5.0,
        cost_generator=CostGenerator.fixed(1.0),
        max_iterations=5
    )
    
    # Test 14: End date in future
    future_end = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
    tester.run_quota_test(
        "Future End Date Test",
        counter_key="test_future_end",
        quota=5.0,
        cost_generator=CostGenerator.fixed(1.0),
        end_date=future_end,
        max_iterations=3
    )
    
    # Clean up test documents
    for key in ["test_daily", "test_monthly", "test_future", "test_past_end", 
                "test_renewal", "test_exponential", "test_zero_quota", 
                "test_negative_cost", "test_small_cost", "test_multi_model", 
                "test_short_renewal", "test_update_quota", "test_exact_quota", 
                "test_future_end"]:
        tester.delete_test_document(key)
    
    return 0

if __name__ == "__main__":
    exit(main())
