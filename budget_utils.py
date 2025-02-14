import json
import os
from typing import Dict, Any

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
