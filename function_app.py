import azure.functions as func
import logging
import json
import os
from openai import AzureOpenAI
from azure.eventhub import EventHubProducerClient, EventData
from datetime import datetime
import httpx
from typing import Any, Dict
import time
import asyncio
from azurefunctions.extensions.http.fastapi import Request, StreamingResponse

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

class HeaderCaptureClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_headers = None

    def send(self, request, *args, **kwargs):
        response = super().send(request, *args, **kwargs)
        self.last_headers = response.headers
        return response

def create_openai_client():
    http_client = HeaderCaptureClient()
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_BASE_URL"],
        http_client=http_client,
    ), http_client

@app.route(route="aoaifn", methods=[func.HttpMethod.POST])
async def aoaifn(req: Request) -> StreamingResponse:
    """
    Azure OpenAI Function that proxies requests to Azure OpenAI API with streaming support.
    """
    logging.info('Processing OpenAI proxy request')
    
    try:
        # Get request parameters
        request_body = await req.json()
        
        # Initialize client with header capture
        client, http_client = create_openai_client()

        # Extract known parameters
        model = request_body.get("model", os.environ["AZURE_OPENAI_MODEL"])
        messages = request_body["messages"]
        stream = request_body.get("stream", False)  # Default to non-streaming
        
        # Filter out known parameters for additional args
        extra_args = {
            k: v for k, v in request_body.items() 
            if k not in ["model", "messages", "stream"]
        }

        # Start timing before API call
        start_time = time.time()

        # Create chat completion
        if stream:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **extra_args
            )
            return await process_openai_stream(response, messages, http_client, start_time)
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                **extra_args
            )
            # Calculate latency including API call
            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)  # Convert to milliseconds
            # Capture headers from the custom client
            headers = http_client.last_headers
            return process_openai_sync(response, messages, headers, latency_ms)

    except Exception as e:
        logging.error(f"Error in proxy function: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            headers={'Content-Type': 'application/json'}
        )

def log_to_eventhub(log_data: dict):
    """Log data to Azure Event Hub"""
    try:
        if "AZURE_EVENTHUB_CONN_STR" not in os.environ:
            logging.info("Event Hub connection string not configured, skipping event hub logging")
            return

        # Create producer
        producer = EventHubProducerClient.from_connection_string(
            conn_str=os.environ["AZURE_EVENTHUB_CONN_STR"],
            eventhub_name=os.environ.get("AZURE_EVENTHUB_NAME", "openai-logs")
        )

        # Add timestamp to log data
        log_data["timestamp"] = datetime.utcnow().isoformat()
        event_data = EventData(json.dumps(log_data))

        # Send event using the correct method
        with producer:
            batch = producer.create_batch()
            batch.add(event_data)
            producer.send_batch(batch)
            
    except Exception as e:
        logging.error(f"Failed to log to Event Hub: {str(e)}")

def process_openai_sync(response, messages, headers, latency_ms):
    """Process non-streaming response from OpenAI"""
    try:
        content = response.choices[0].message.content
        
        if response.usage:
            log_data = {
                "type": "completion",
                "content": content,
                "usage": response.usage.model_dump(),
                "model": response.model,
                "prompt": messages,
                "region": headers.get("x-ms-region", "unknown"),
                "latency_ms": latency_ms
            }
            log_to_eventhub(log_data)

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

async def process_openai_stream(response, messages, http_client, start_time):
    """Process streaming response from OpenAI"""
    headers = http_client.last_headers
    processor = ResponseProcessor(messages, headers)

    async def generate():
        for chunk in response:
            chunk_text = processor.process_chunk(chunk)
            if chunk_text:
                yield chunk_text

    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

class ResponseProcessor:
    def __init__(self, messages, headers):
        self.response_body = []
        self.all_chunks = []
        self.messages = messages
        self.region = headers.get("x-ms-region", "unknown")
        self.start_time = time.time()

    def process_chunk(self, chunk):
        """Process individual chunk from OpenAI response"""
        try:
            # Handle usage data
            if hasattr(chunk, 'usage') and chunk.usage is not None:
                end_time = time.time()
                latency_ms = int((end_time - self.start_time) * 1000)  # Convert to milliseconds
                complete_message = ''.join(self.all_chunks)
                
                log_data = {
                    "type": "stream_completion",
                    "content": complete_message,
                    "usage": chunk.usage.model_dump(),
                    "model": chunk.model,
                    "prompt": self.messages,
                    "region": self.region,
                    "latency_ms": latency_ms
                }
                log_to_eventhub(log_data)

                # Handle usage data
                logging.info(f"Complete message: {complete_message}")
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