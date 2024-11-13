# Azure OpenAI Proxy Function

This Azure Function acts as a proxy for Azure OpenAI, supporting both streaming and non-streaming responses. It provides a simple way to interact with Azure OpenAI services while handling both Server-Sent Events (SSE) streaming and standard JSON responses.

This is to resolve Event Hub Logging for  [APIM SSE Streaming limitation](https://learn.microsoft.com/en-us/azure/api-management/how-to-server-sent-events).

## Setup

### Prerequisites
- Azure subscription
- Azure Function App (Python)
- Azure OpenAI service instance

### Environment Variables
Set the following environment variables in your Azure Function App:

```bash
az functionapp config appsettings set \
  --name fnsse \
  --resource-group fnsse \
  --settings \
  "AZURE_OPENAI_KEY=your_key_here" \
  "AZURE_OPENAI_API_VERSION=2024-08-01-preview" \
  "AZURE_OPENAI_BASE_URL=https://your-instance.openai.azure.com/" \
  "AZURE_OPENAI_MODEL=deployment-name" \
  "AZURE_EVENTHUB_CONN_STR=your_eventhub_connection_string" \
  "AZURE_EVENTHUB_NAME=openai-logs"
```

## Usage

### Endpoint
```http
POST /api/aoaifn
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
Server-Sent Events (SSE) format with content chunks and usage data:
```
data: {"choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"choices":[{"delta":{"content":"Singapore"},"index":0}]}

data: {"choices":[{"delta":{"content":" is"},"index":0}]}

... more chunks ...

data: {"usage":{"completion_tokens":31,"prompt_tokens":25,"total_tokens":56}}

data: [DONE]
```

## Dependencies
- Python 3.9+
- `openai>=1.0.0`
- `azure-functions`

## Deployment
```bash
func azure functionapp publish fnsse
```

## Monitoring
View logs using Azure CLI:
```bash
az functionapp logs tail --name fnsse --resource-group fnsse
```

## Features

### Event Hub Logging
The function automatically logs completion details to Azure Event Hub, including:
- Completion content
- Token usage statistics
- Model information
- Azure region
- Latency metrics
- Original prompt
#### Streaming response log example:
```json
{
    "type": "stream_completion",
    "content": "Singapore is a vibrant city-state located at the southern tip of the Malay Peninsula in Southeast Asia. Known for its impressive skyline, bustling port, and thriving financial sector, Singapore is a global commerce, finance, and transport hub. The country is renowned for its strict laws and immaculate cleanliness, contributing to its status as one of the safest and most orderly places in the world. It has a diverse, multicultural population comprising mainly Chinese, Malay, Indian, and expatriate communities, reflecting its historical role as a trade nexus. Renowned attractions such as Marina Bay Sands, Gardens by the Bay, and Sentosa Island draw millions of tourists annually, adding to its allure as a leading travel destination.",
    "usage": {
        "completion_tokens": 137,
        "prompt_tokens": 25,
        "total_tokens": 162,
        "completion_tokens_details": null,
        "prompt_tokens_details": null
    },
    "model": "gpt-4o-2024-05-13",
    "prompt": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "tell me about Singapore in 5 sentences"
        }
    ],
    "region": "Australia East",
    "latency_ms": 1306,
    "timestamp": "2024-11-13T06:59:30.584946"
}
```
#### Non-streaming response log example:
```json
{
    "type": "completion",
    "content": "Singapore is a sovereign city-state and island country in Southeast Asia. It is known for its highly developed free-market economy, which ranks as one of the most open and competitive globally. Despite its small geographical size, Singapore boasts a high standard of living and is a major financial hub with a strong international presence. The nation's strategic location has fostered a diverse, multicultural population, contributing to a rich cultural tapestry. Singapore is also recognized for its efficient and advanced infrastructure, including a world-renowned public transportation system and a highly regarded healthcare system.",
    "usage": {
        "completion_tokens": 106,
        "prompt_tokens": 25,
        "total_tokens": 131,
        "completion_tokens_details": null,
        "prompt_tokens_details": null
    },
    "model": "gpt-4o-2024-05-13",
    "prompt": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "tell me about Singapore in 5 sentences"
        }
    ],
    "region": "Australia East",
    "latency_ms": 1738,
    "timestamp": "2024-11-13T07:00:06.449374"
}
```


### Region Tracking
The function captures and logs the Azure region where the request was processed using response headers.

### Latency Monitoring
Request latency is tracked and logged for both streaming and non-streaming responses.