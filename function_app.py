import azure.functions as func
import logging
import json
import os
from openai import AzureOpenAI
import httpx
import time
from datetime import datetime
from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential
from azurefunctions.extensions.http.fastapi import Request, StreamingResponse
from fastapi.responses import JSONResponse
from eventhub_cosmos_blueprint import blueprint
from budget_manager import CustomBudgetManager

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
app.register_functions(blueprint) 

# Initialize budget manager
budget_manager = CustomBudgetManager()

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

# Initialize Event Hub producer client
eventhub_producer = None
def get_eventhub_producer():
    global eventhub_producer
    if eventhub_producer is None:
        try:
            eventhub_name = os.environ.get("AZURE_EVENTHUB_NAME", "eh-fnsse-w7yorq49")
            namespace = os.environ.get("EventHubConnection_fullyQualifiedNamespace", "ehns-fnsse-w7yorq49.servicebus.windows.net")
            
            # Try connection string first (local development)
            if "EventHubConnection" in os.environ:
                eventhub_producer = EventHubProducerClient.from_connection_string(
                    conn_str=os.environ["EventHubConnection"]
                )
                logging.info("Created Event Hub producer using connection string")
            # Fall back to MSI (Azure deployment)
            else:
                credential = DefaultAzureCredential()
                eventhub_producer = EventHubProducerClient(
                    fully_qualified_namespace=namespace,
                    eventhub_name=eventhub_name,
                    credential=credential
                )
                logging.info(f"Created Event Hub producer using MSI authentication: {namespace}/{eventhub_name}")
        except Exception as e:
            logging.error(f"Failed to create Event Hub producer: {str(e)}")
            return None
    return eventhub_producer

def log_to_eventhub(log_data: dict):
    """Log data to Azure Event Hub"""
    try:
        producer = get_eventhub_producer()
        if producer is None:
            logging.info("Event Hub producer not available, skipping event hub logging")
            return

        # Add timestamp to log data
        log_data["timestamp"] = datetime.utcnow().isoformat()
        event_data = EventData(json.dumps(log_data))

        # Send event using the correct method
        batch = producer.create_batch()
        batch.add(event_data)
        producer.send_batch(batch)
        logging.info(f"Successfully logged to Event Hub: {log_data}")
    except Exception as e:
        logging.error(f"Failed to log to Event Hub: {str(e)}")
        # If we get a connection error, clear the producer so it can be recreated
        if "connection" in str(e).lower():
            global eventhub_producer
            eventhub_producer = None

@app.function_name(name="chat_completion_proxy")
@app.route(route="openai/deployments/{deployment_name}/chat/completions", 
          methods=[func.HttpMethod.POST],
          auth_level=func.AuthLevel.FUNCTION)
async def chat_completion_proxy(req: Request) -> StreamingResponse:
    """
    Azure OpenAI Function that proxies requests to Azure OpenAI API with streaming support.
    Matches the official Azure OpenAI API signature.
    """
    logging.info('Processing OpenAI proxy request')
    
    try:
        # Get request parameters
        request_body = await req.json()
        logging.info(f"Request body: {json.dumps(request_body)}")
        
        # Extract user ID from request body or use default
        user_id = request_body.get("user", "default_user")
        
        # Setup budget for user if not already set
        try:
            budget_manager.setup_user_budget(user_id=user_id, total_budget=10.0)
        except Exception as e:
            logging.warning(f"Budget already exists for user {user_id}: {str(e)}")
        
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
        
        # Log the incoming request
        # request_log = {
        #     "type": "request",
        #     "timestamp": datetime.utcnow().isoformat(),
        #     "messages": messages,
        #     "user_id": user_id
        # }
        # event.set(json.dumps(request_log))
        
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
            return await process_openai_sync(response, messages, headers, latency_ms)

    except Exception as e:
        logging.error(f"Error in proxy function: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

async def process_openai_sync(response, messages, headers, latency_ms):
    """Process non-streaming response from OpenAI"""
    try:
        content = response.choices[0].message.content
        user_id = messages[0].get("user", "default_user") if messages else "default_user"
        
        # Track cost using budget manager
        try:
            current_cost = budget_manager.track_request_cost(
                user_id=user_id,
                model=response.model,
                input_text=str(messages),
                output_text=content
            )
            logging.info(f"Current cost for user {user_id}: {current_cost}")
        except Exception as e:
            logging.error(f"Error tracking cost: {str(e)}")
        
        if response.usage:
            # Add cost and user_id to usage data
            usage_data = response.usage.model_dump()
            usage_data["current_cost"] = current_cost if 'current_cost' in locals() else None
            usage_data["user_id"] = user_id
            
            log_data = {
                "type": "completion",
                "content": content,
                "usage": usage_data,
                "model": response.model,
                "prompt": messages,
                "region": headers.get("x-ms-region", "unknown"),
                "latency_ms": latency_ms,
                "user_id": user_id
            }
            log_to_eventhub(log_data)

        # Modify the response to include cost and user_id in usage
        response_data = response.model_dump()
        if 'usage' in response_data:
            if 'current_cost' in locals():
                response_data['usage']['current_cost'] = current_cost
            response_data['usage']['user_id'] = user_id

        # Return JSONResponse directly
        return JSONResponse(
            content=response_data,
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
    first_chunk_time = None
    user_id = messages[0].get("user", "default_user") if messages else "default_user"

    async def generate():
        try:
            for chunk in response:
                chunk_dict = chunk.model_dump()
                
                # Track first chunk timing
                nonlocal first_chunk_time
                if first_chunk_time is None:
                    first_chunk_time = time.time()

                # Collect content for logging
                if chunk.choices and chunk.choices[0].delta.content:
                    content_buffer.append(chunk.choices[0].delta.content)
                
                # Capture model name and usage if present
                if hasattr(chunk, 'model'):
                    nonlocal model_name
                    model_name = chunk.model

                # Calculate cost and update usage if present
                if hasattr(chunk, 'usage') and chunk.usage:
                    nonlocal usage_data
                    usage_dict = chunk.usage.model_dump()
                    usage_dict["user_id"] = user_id
                    
                    # Track cost when we have usage data
                    try:
                        current_cost = budget_manager.track_request_cost(
                            user_id=user_id,
                            model=model_name or "gpt-4",
                            input_text=str(messages),
                            output_text=''.join(content_buffer)
                        )
                        usage_dict["current_cost"] = current_cost
                    except Exception as e:
                        logging.error(f"Error tracking streaming cost: {str(e)}")
                        usage_dict["current_cost"] = None
                    
                    chunk_dict['usage'] = usage_dict
                    usage_data = usage_dict

                # Send chunk exactly as received from OpenAI
                yield f"data: {json.dumps(chunk_dict)}\n\n"
                                

        except Exception as e:
            logging.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Calculate timing metrics
            last_chunk_time = time.time()
            time_to_first_chunk = int((first_chunk_time - start_time) * 1000) if first_chunk_time else None
            streaming_duration = int((last_chunk_time - first_chunk_time) * 1000) if first_chunk_time else None
            latency_ms = int((last_chunk_time - start_time) * 1000)

            # Log to EventHub before sending DONE
            try:
                if content_buffer:  # Only log if we have content
                    full_content = "".join(content_buffer)
                    
                    log_data = {
                        "type": "stream_completion",
                        "content": full_content,
                        "model": model_name or "unknown",
                        "usage": usage_data,
                        "prompt": messages,
                        "region": headers.get("x-ms-region", "unknown"),
                        "latency_ms": latency_ms,
                        "time_to_first_chunk_ms": time_to_first_chunk,
                        "streaming_duration_ms": streaming_duration,
                        "user_id": user_id
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