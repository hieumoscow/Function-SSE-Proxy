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
  "AZURE_OPENAI_MODEL=deployment-name"
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