#!/bin/bash

# Test script for all Fleet Optimization API endpoints
# Usage: ./test_all_endpoints.sh

API_URL="${1:-http://localhost:8000}"

echo "Testing Fleet Optimization API at: ${API_URL}"
echo "=========================================="

echo -e "\n[1/4] Testing Root Endpoint..."
curl -s "${API_URL}/" | jq '.' 2>/dev/null || curl -s "${API_URL}/"

echo -e "\n[2/4] Testing Health Check..."
curl -s "${API_URL}/health" | jq '.' 2>/dev/null || curl -s "${API_URL}/health"

echo -e "\n[3/4] Testing Database Info..."
curl -s "${API_URL}/db/info" | jq '.' 2>/dev/null || curl -s "${API_URL}/db/info"

echo -e "\n[4/4] Testing Full Optimization..."
if [ -f "algorithm_config.json" ]; then
    echo "Using algorithm_config.json..."
    curl -s -X POST "${API_URL}/algorithm/run" \
      -H "Content-Type: application/json" \
      -d @algorithm_config.json | jq '.' 2>/dev/null || \
    curl -s -X POST "${API_URL}/algorithm/run" \
      -H "Content-Type: application/json" \
      -d @algorithm_config.json
else
    echo "⚠️  algorithm_config.json not found, skipping optimization test"
fi

echo -e "\n=========================================="
echo "✅ All tests completed!"

