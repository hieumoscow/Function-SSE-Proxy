import azure.functions as func
import logging
import json
import os
from openai import AzureOpenAI

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="aoaifn")
async def aoaifn(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure OpenAI Function that proxies requests to Azure OpenAI API with streaming support.
    """
    logging.info('Processing OpenAI proxy request')
    
    try:
        # Get request parameters
        request_body = req.get_json()
        
        # Initialize Azure OpenAI client
        client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_endpoint=os.environ["AZURE_OPENAI_BASE_URL"]
        )

        # Extract known parameters
        model = request_body.get("model", os.environ["AZURE_OPENAI_MODEL"])
        messages = request_body["messages"]
        stream = request_body.get("stream", False)  # Default to non-streaming
        
        # Filter out known parameters for additional args
        extra_args = {
            k: v for k, v in request_body.items() 
            if k not in ["model", "messages", "stream"]
        }

        # Create chat completion
        if stream:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **extra_args
            )
            return await process_openai_stream(response)
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                **extra_args
            )
            return process_openai_sync(response)

    except Exception as e:
        logging.error(f"Error in proxy function: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            headers={'Content-Type': 'application/json'}
        )

def process_openai_sync(response):
    """Process non-streaming response from OpenAI"""
    try:
        # Log the complete message and usage
        content = response.choices[0].message.content
        logging.info(f"Complete message: {content}")
        
        if response.usage:
            logging.info(f"Usage details:")
            logging.info(f"  Completion tokens: {response.usage.completion_tokens}")
            logging.info(f"  Prompt tokens: {response.usage.prompt_tokens}")
            logging.info(f"  Total tokens: {response.usage.total_tokens}")

        # Return the response
        return func.HttpResponse(
            body=json.dumps(response.model_dump()),
            status_code=200,
            headers={'Content-Type': 'application/json'}
        )

    except Exception as e:
        logging.error(f"Error processing sync response: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            headers={'Content-Type': 'application/json'}
        )

async def process_openai_stream(response):
    """Process streaming response from OpenAI"""
    processor = ResponseProcessor()
    response_body = []

    try:
        for chunk in response:
            chunk_text = processor.process_chunk(chunk)
            if chunk_text:
                response_body.append(chunk_text)

        return func.HttpResponse(
            body=''.join(response_body).encode('utf-8'),
            status_code=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        logging.error(f"Error processing stream: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            headers={'Content-Type': 'application/json'}
        )

class ResponseProcessor:
    def __init__(self):
        self.response_body = []
        self.all_chunks = []

    def process_chunk(self, chunk):
        """Process individual chunk from OpenAI response"""
        try:
            # Handle usage data
            if hasattr(chunk, 'usage') and chunk.usage is not None:
                logging.info(f"Complete message: {''.join(self.all_chunks)}")
                logging.info(f"Usage details:")
                logging.info(f"  Completion tokens: {chunk.usage.completion_tokens}")
                logging.info(f"  Prompt tokens: {chunk.usage.prompt_tokens}")
                logging.info(f"  Total tokens: {chunk.usage.total_tokens}")
                chunk_dict = chunk.model_dump()
                return f"data: {json.dumps(chunk_dict)}\n\ndata: [DONE]\n\n"

            # Handle content filter results
            if not chunk.choices and hasattr(chunk, 'prompt_filter_results'):
                return None

            # Check if chunk has choices
            if not chunk.choices:
                logging.warning(f"Received chunk without choices: {chunk}")
                return None

            delta = chunk.choices[0].delta
            
            # Handle content updates
            if hasattr(delta, 'content') and delta.content is not None:
                self.all_chunks.append(delta.content)
                chunk_dict = chunk.model_dump()
                return f"data: {json.dumps(chunk_dict)}\n\n"
            
            # Handle role messages (usually first message)
            elif hasattr(delta, 'role'):
                chunk_dict = chunk.model_dump()
                return f"data: {json.dumps(chunk_dict)}\n\n"
            
            return None

        except Exception as e:
            logging.error(f"Error processing chunk: {str(e)}")
            logging.error(f"Problematic chunk: {chunk}")
            return None