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
from azurefunctions.extensions.http.fastapi import Request, StreamingResponse
from fastapi.responses import JSONResponse

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

@app.route(route="openai/deployments/{deployment_name}/chat/completions", methods=[func.HttpMethod.POST])
async def aoaifn(req: Request) -> StreamingResponse:
    """
    Azure OpenAI Function that proxies requests to Azure OpenAI API with streaming support.
    Matches the official Azure OpenAI API signature.
    """
    logging.info('Processing OpenAI proxy request')
    
    try:
        # Get request parameters
        request_body = await req.json()
        logging.info(f"Request body: {json.dumps(request_body)}")  # Log the request body
        
        # Get API version from query parameters
        api_version = req.query_params.get("api-version")
        if not api_version:
            return JSONResponse(
                content={"error": "api-version is required"},
                status_code=400
            )

        # Get deployment name from path parameters
        deployment_name = req.path_params.get("deployment_name")
        if not deployment_name:
            return JSONResponse(
                content={"error": "deployment_name is required"},
                status_code=400
            )

        # Initialize client with header capture
        client, http_client = create_openai_client()

        # Extract stream parameter
        messages = request_body["messages"]
        stream = request_body.get("stream", False)
        
        # Filter out only the stream parameter for extra args
        extra_args = {
            k: v for k, v in request_body.items() 
            if k not in ["messages", "stream"]  # Remove stream_options from the filter
        }
        
        logging.info(f"Extra args being passed to OpenAI: {json.dumps(extra_args)}")  # Log extra args

        # Start timing before API call
        start_time = time.time()

        # Create chat completion
        if stream:
            response = client.chat.completions.create(
                model=deployment_name,
                messages=messages,
                stream=True,
                **extra_args  # This will now include stream_options
            )
            return await process_openai_stream(response, messages, http_client, start_time)
        else:
            response = client.chat.completions.create(
                model=deployment_name,
                messages=messages,
                stream=False,
                **extra_args
            )
            # Calculate latency including API call
            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)
            headers = http_client.last_headers
            return process_openai_sync(response, messages, headers, latency_ms)

    except Exception as e:
        logging.error(f"Error in proxy function: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

def log_to_eventhub(log_data: dict):
    """Log data to Azure Event Hub"""
    try:
        if "AZURE_EVENTHUB_CONN_STR" not in os.environ:
            logging.info("Event Hub connection string not configured, skipping event hub logging")
            return

        # Create producer
        producer = EventHubProducerClient.from_connection_string(
            conn_str=os.environ["AZURE_EVENTHUB_CONN_STR"]
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

        # Return JSONResponse directly
        return JSONResponse(
            content=response.model_dump(),
            headers={
                'x-ms-region': headers.get("x-ms-region", "unknown")
            }
        )

    except Exception as e:
        logging.error(f"Error processing sync response: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

async def process_openai_stream(response, messages, http_client, start_time):
    """Process streaming response from OpenAI"""
    headers = http_client.last_headers
    content_buffer = []
    usage_data = None
    model_name = None

    async def generate():
        try:
            for chunk in response:
                chunk_dict = chunk.model_dump()
                
                # Collect content for logging
                if chunk.choices and chunk.choices[0].delta.content:
                    content_buffer.append(chunk.choices[0].delta.content)
                
                # Capture model name and usage if present
                if hasattr(chunk, 'model'):
                    nonlocal model_name
                    model_name = chunk.model
                if hasattr(chunk, 'usage') and chunk.usage:
                    nonlocal usage_data
                    usage_data = chunk.usage.model_dump()

                # Send chunk exactly as received from OpenAI
                yield f"data: {json.dumps(chunk_dict)}\n\n"

        except Exception as e:
            logging.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Log to EventHub before sending DONE
            try:
                end_time = time.time()
                latency_ms = int((end_time - start_time) * 1000)
                
                if content_buffer:  # Only log if we have content
                    log_data = {
                        "type": "stream_completion",
                        "content": "".join(content_buffer),
                        "model": model_name or "unknown",
                        "usage": usage_data,  # This might be None if no usage data was received
                        "prompt": messages,
                        "region": headers.get("x-ms-region", "unknown"),
                        "latency_ms": latency_ms
                    }
                    logging.info(f"Logging streaming completion to EventHub: {json.dumps(log_data)}")
                    log_to_eventhub(log_data)
            except Exception as e:
                logging.error(f"Failed to log to EventHub: {str(e)}")
            
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'x-ms-region': headers.get("x-ms-region", "unknown")
        }
    )