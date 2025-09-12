"""
LLM Client utility for unified model access across providers.
Supports OpenAI and Claude with configurable model selection.
"""
import os
import json
from typing import Dict, Any, List, Optional
from flask import current_app
import openai


class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
    def __init__(self):
        self.provider = current_app.config.get('LLM_PROVIDER', 'openai')
        self.model_name = current_app.config.get('MODEL_NAME', 'gpt-4.1-mini')
        self.test_mode = os.getenv('LLM_TEST_MODE', 'false').lower() == 'true'
        
        if self.test_mode:
            # In test mode, don't initialize real clients
            self.client = None
        elif self.provider == 'openai':
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key and not self.test_mode:
                # Only require API key when not in test mode
                raise ValueError("OPENAI_API_KEY environment variable is required when using OpenAI provider")
            self.client = openai.OpenAI(
                api_key=api_key or "test-key",
                base_url=os.getenv('OPENAI_API_BASE')
            ) if not self.test_mode else None
        elif self.provider == 'claude':
            # Claude client setup - placeholder for now
            self.client = None
            self.api_key = os.getenv('CLAUDE_API_KEY')
            if not self.api_key:
                raise ValueError("CLAUDE_API_KEY environment variable is required when using Claude provider")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """
        Generate a chat completion using the configured provider and model.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            temperature: Sampling temperature (0.0 to 1.0)
            
        Returns:
            The generated response content as a string
        """
        if self.test_mode:
            return self._generate_test_response(messages)
        elif self.provider == 'openai':
            return self._openai_completion(messages, temperature)
        elif self.provider == 'claude':
            return self._claude_completion(messages, temperature)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _openai_completion(self, messages: List[Dict[str, str]], temperature: float) -> str:
        """Generate completion using OpenAI API."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=4000
            )
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    def _claude_completion(self, messages: List[Dict[str, str]], temperature: float) -> str:
        """Generate completion using Claude API."""
        # Placeholder implementation for Claude
        # In a real implementation, you would use the Anthropic client library
        raise NotImplementedError("Claude provider not yet implemented")
    
    def _generate_test_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate predictable test responses based on prompt content."""
        prompt = messages[0]['content'].lower() if messages else ''
        
        if 'categorize' in prompt or 'three categories' in prompt:
            # Categorization response
            return json.dumps({
                "categories": {
                    "industry": ["test-industry-keyword"],
                    "company": ["test-company-keyword"], 
                    "regulatory": ["test-regulatory-keyword"]
                },
                "explanations": {
                    "industry": "Test industry terms for validation",
                    "company": "Test company terms for validation",
                    "regulatory": "Test regulatory terms for validation"
                }
            })
        
        elif 'expand' in prompt or 'additional relevant' in prompt:
            # Expansion response  
            return json.dumps({
                "expanded": {
                    "industry": ["test-industry-keyword", "expanded-industry-term"],
                    "company": ["test-company-keyword", "expanded-company-term"],
                    "regulatory": ["test-regulatory-keyword", "expanded-regulatory-term"]
                },
                "notes": "Test expansion with predictable additional terms"
            })
        
        elif 'drop' in prompt or 'outdated' in prompt or 'remove' in prompt:
            # Drop outdated response
            return json.dumps({
                "updated": {
                    "industry": ["test-industry-keyword"],
                    "company": ["test-company-keyword"],
                    "regulatory": ["test-regulatory-keyword"]
                },
                "removed": [
                    {"term": "expanded-industry-term", "reason": "Test removal for validation"},
                    {"term": "expanded-company-term", "reason": "Another test removal"}
                ],
                "justification": "Test justification for removing outdated terms"
            })
        
        else:
            # Default fallback response
            return json.dumps({
                "categories": {
                    "industry": ["fallback-industry"],
                    "company": ["fallback-company"],
                    "regulatory": ["fallback-regulatory"]
                },
                "explanations": {
                    "industry": "Fallback response",
                    "company": "Fallback response", 
                    "regulatory": "Fallback response"
                }
            })
    
    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON response from LLM, with error handling.
        
        Args:
            response: Raw response string from LLM
            
        Returns:
            Parsed JSON as dictionary
            
        Raises:
            ValueError: If response is not valid JSON
        """
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Failed to parse JSON response: {response}")
            raise ValueError(f"Invalid JSON response from LLM: {str(e)}")


def get_llm_client() -> LLMClient:
    """Get a configured LLM client instance."""
    return LLMClient()

