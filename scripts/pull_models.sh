#!/bin/bash
set -e

OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434}"
OCR_MODEL="${OCR_MODEL:-deepseek-r1}"
SCAFFOLDING_MODEL="${SCAFFOLDING_MODEL:-llama3}"

echo "Waiting for Ollama to be ready..."
until curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1; do
    sleep 2
done

echo "Pulling OCR model: $OCR_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\": \"$OCR_MODEL\"}"

echo "Pulling scaffolding model: $SCAFFOLDING_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\": \"$SCAFFOLDING_MODEL\"}"

echo "Models ready."
