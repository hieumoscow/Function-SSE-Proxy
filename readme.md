# Azure OpenAI Proxy Function

This Azure Function acts as a proxy for Azure OpenAI, supporting both streaming and non-streaming responses. It provides a simple way to interact with Azure OpenAI services while handling both Server-Sent Events (SSE) streaming and standard JSON responses.

This is to resolve Event Hub Logging for [APIM SSE Streaming limitation](https://learn.microsoft.com/en-us/azure/api-management/how-to-server-sent-events).

## Setup

### Prerequisites
- Azure subscription
- Azure Function App (Python)
- Azure OpenAI service instance

### Environment Variables
Copy `local.settings.sample.json` to `local.settings.json` and set the following environment variables:
or
Set the following environment variables in your Azure Function App:

```bash
az functionapp config appsettings set \
  --name fnsse \
  --resource-group fnsse \
  --settings \
  "AZURE_OPENAI_KEY=your_key_here" \
  "AZURE_OPENAI_API_VERSION=2024-08-01-preview" \
  "AZURE_OPENAI_BASE_URL=https://your-instance.openai.azure.com/" \
  "AZURE_EVENTHUB_CONN_STR=your_eventhub_connection_string" \
  "AZURE_EVENTHUB_NAME=openai-logs" \
  "PYTHON_ENABLE_INIT_INDEXING=1"
```

> Note: `PYTHON_ENABLE_INIT_INDEXING=1` is required for proper Python module initialization in Azure Functions.

## Demo

### Function Start
![Start](./assets/FNSSEStart.gif)
### API Call
![API Call](./assets/FNSSEAPI.gif)
### Event Hub
![Event Hub](./assets/FNSSEEventHub.gif)


## Usage

### Endpoint
The endpoint matches the Azure OpenAI API signature:
```http
POST /openai/deployments/{deployment_name}/chat/completions?api-version=2024-08-01-preview
```

### Request Format

#### Non-streaming Request (Default)
```json
{
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Tell me about Singapore in 1 sentence"
        }
    ]
}
```

#### Streaming Request
```json
{
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Tell me about Singapore in 1 sentence"
        }
    ],
    "stream": true,
    "stream_options": {
        "include_usage": true
    }
}
```

### Response Format

#### Non-streaming Response
Standard Azure OpenAI response format:
```json
{
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "created": 1677652288,
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "Singapore is a highly developed city-state..."
        },
        "finish_reason": "stop"
    }],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 31,
        "total_tokens": 56
    }
}
```

#### Streaming Response
Server-Sent Events (SSE) format with chunks matching Azure OpenAI's format:
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"choices":[{"index":0,"delta":{"role":"assistant"}}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"choices":[{"index":0,"delta":{"content":"Singapore"}}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"choices":[{"index":0,"delta":{"content":" is"}}]}

... more chunks ...

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"usage":{"completion_tokens":31,"prompt_tokens":25,"total_tokens":56}}

data: [DONE]
```

## Event Hub Logging
The function automatically logs completion details to Azure Event Hub for both streaming and non-streaming responses:

### Non-streaming Log Format
```json
{
    "type": "completion",
    "content": "Singapore is a vibrant city-state...",
    "usage": {
        "completion_tokens": 137,
        "prompt_tokens": 25,
        "total_tokens": 162
    },
    "model": "gpt-4",
    "prompt": [...],
    "region": "Australia East",
    "latency_ms": 1306,
    "timestamp": "2024-11-13T06:59:30.584946"
}
```

### Streaming Log Format
```json
{
    "type": "stream_completion",
    "content": "Singapore is a vibrant city-state...",
    "model": "gpt-4o",
    "usage": {
        "completion_tokens": 137,
        "prompt_tokens": 25,
        "total_tokens": 162
    },
    "prompt": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Tell me about Singapore in 1 sentence"
        }
    ],
    "region": "Australia East",
    "latency_ms": 2650,
    "time_to_first_chunk_ms": 150,
    "streaming_duration_ms": 2500,
    "timestamp": "2024-11-13T06:59:30.584946"
}
```

### Understanding Timing Metrics
For streaming responses, three timing metrics are captured:

- `time_to_first_chunk_ms`: Time from request start until first token (includes queue time and model startup)
- `streaming_duration_ms`: Duration of token generation (actual model inference time)
- `latency_ms`: Total request duration (time_to_first_chunk_ms + streaming_duration_ms)

These metrics help identify:
- Queue waiting time in different regions
- Model warm-up and startup time
- Token generation speed
- Overall request latency

## Dependencies
- Python 3.9+
- `openai>=1.0.0`
- `azure-functions`
- `azure.functions.extensions.http.fastapi`
- `httpx`

## Deployment
```bash
func azure functionapp publish fnsse
```

## Monitoring
View logs using Azure CLI:
```bash
az functionapp logs tail --name fnsse --resource-group fnsse
```