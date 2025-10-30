# API Endpoint CURL Examples

This document contains working curl commands for all Fleet Optimization API endpoints.

## Base URL
```bash
API_URL="http://localhost:8000"
```

---

## Health & Status Endpoints

### 1. Root Endpoint (API Info)
```bash
curl -X GET "${API_URL}/"
```

### 2. Health Check
```bash
curl -X GET "${API_URL}/health"
```

### 3. Database Info
```bash
curl -X GET "${API_URL}/db/info"
```

---

## CSV Upload Endpoints (Multipart)

### 4. Validate CSV Files
Upload all 5 CSV files + config for validation only:

```bash
curl -X POST "${API_URL}/upload/validate" \
  -F "locations=@data/locations.csv" \
  -F "locations_relations=@data/locations_relations.csv" \
  -F "routes=@data/routes.csv" \
  -F "segments=@data/segments.csv" \
  -F "vehicles=@data/vehicles.csv" \
  -F "config=@algorithm_config.json"
```

### 5. Process CSV Files
Upload all 5 CSV files + config for processing:

```bash
curl -X POST "${API_URL}/upload/process" \
  -F "locations=@data/locations.csv" \
  -F "locations_relations=@data/locations_relations.csv" \
  -F "routes=@data/routes.csv" \
  -F "segments=@data/segments.csv" \
  -F "vehicles=@data/vehicles.csv" \
  -F "config=@algorithm_config.json"
```

### 6. Import CSV Files to Database
Upload all 5 CSV files directly to database:

```bash
curl -X POST "${API_URL}/upload/import" \
  -F "locations=@data/locations.csv" \
  -F "locations_relations=@data/locations_relations.csv" \
  -F "routes=@data/routes.csv" \
  -F "segments=@data/segments.csv" \
  -F "vehicles=@data/vehicles.csv"
```

---

## Algorithm Endpoints

All algorithm endpoints accept JSON config in the request body and pull data from the database.

### 7. Run Placement Algorithm Only

```bash
curl -X POST "${API_URL}/algorithm/placement" \
  -H "Content-Type: application/json" \
  -d '{
    "data_dir": "./data",
    "output_dir": "./output",
    "placement": {
      "strategy": "cost_based",
      "lookahead_days": 7,
      "max_concentration": 0.3,
      "max_vehicles_per_location": null
    },
    "assignment": {
      "strategy": "greedy_optimized",
      "assignment_lookahead_days": 14,
      "look_ahead_days": 7,
      "chain_depth": 3,
      "chain_weight": 0.3,
      "max_lookahead_routes": 100,
      "use_chain_optimization": true
    },
    "swap_policy": {
      "max_swaps_per_period": 10,
      "swap_period_days": 30
    },
    "service_policy": {
      "service_tolerance_km": 1000,
      "service_duration_hours": 8,
      "service_penalty_pln": 500.0,
      "service_cost_pln": 300.0
    },
    "costs": {
      "relocation_base_cost_pln": 100.0,
      "relocation_per_km_pln": 2.0,
      "relocation_per_hour_pln": 50.0,
      "overage_per_km_pln": 5.0
    },
    "performance": {
      "progress_report_days": 7,
      "progress_report_interval": 10,
      "use_pathfinding": true,
      "use_relation_cache": true
    }
  }'
```

### 8. Run Assignment Algorithm Only

```bash
curl -X POST "${API_URL}/algorithm/assignment" \
  -H "Content-Type: application/json" \
  -d '{
    "data_dir": "./data",
    "output_dir": "./output",
    "placement": {
      "strategy": "cost_based",
      "lookahead_days": 7,
      "max_concentration": 0.3,
      "max_vehicles_per_location": null
    },
    "assignment": {
      "strategy": "greedy_optimized",
      "assignment_lookahead_days": 14,
      "look_ahead_days": 7,
      "chain_depth": 3,
      "chain_weight": 0.3,
      "max_lookahead_routes": 100,
      "use_chain_optimization": true
    },
    "swap_policy": {
      "max_swaps_per_period": 10,
      "swap_period_days": 30
    },
    "service_policy": {
      "service_tolerance_km": 1000,
      "service_duration_hours": 8,
      "service_penalty_pln": 500.0,
      "service_cost_pln": 300.0
    },
    "costs": {
      "relocation_base_cost_pln": 100.0,
      "relocation_per_km_pln": 2.0,
      "relocation_per_hour_pln": 50.0,
      "overage_per_km_pln": 5.0
    },
    "performance": {
      "progress_report_days": 7,
      "progress_report_interval": 10,
      "use_pathfinding": true,
      "use_relation_cache": true
    }
  }'
```

### 9. Run Full Optimization (Placement + Assignment)

```bash
curl -X POST "${API_URL}/algorithm/run" \
  -H "Content-Type: application/json" \
  -d '{
    "data_dir": "./data",
    "output_dir": "./output",
    "placement": {
      "strategy": "cost_based",
      "lookahead_days": 7,
      "max_concentration": 0.3,
      "max_vehicles_per_location": null
    },
    "assignment": {
      "strategy": "greedy_optimized",
      "assignment_lookahead_days": 14,
      "look_ahead_days": 7,
      "chain_depth": 3,
      "chain_weight": 0.3,
      "max_lookahead_routes": 100,
      "use_chain_optimization": true
    },
    "swap_policy": {
      "max_swaps_per_period": 10,
      "swap_period_days": 30
    },
    "service_policy": {
      "service_tolerance_km": 1000,
      "service_duration_hours": 8,
      "service_penalty_pln": 500.0,
      "service_cost_pln": 300.0
    },
    "costs": {
      "relocation_base_cost_pln": 100.0,
      "relocation_per_km_pln": 2.0,
      "relocation_per_hour_pln": 50.0,
      "overage_per_km_pln": 5.0
    },
    "performance": {
      "progress_report_days": 7,
      "progress_report_interval": 10,
      "use_pathfinding": true,
      "use_relation_cache": true
    }
  }'
```

---

## Using Config from File

You can also load the JSON config from your `algorithm_config.json` file:

### Placement from Config File
```bash
curl -X POST "${API_URL}/algorithm/placement" \
  -H "Content-Type: application/json" \
  -d @algorithm_config.json
```

### Assignment from Config File
```bash
curl -X POST "${API_URL}/algorithm/assignment" \
  -H "Content-Type: application/json" \
  -d @algorithm_config.json
```

### Full Optimization from Config File
```bash
curl -X POST "${API_URL}/algorithm/run" \
  -H "Content-Type: application/json" \
  -d @algorithm_config.json
```

---

## Pretty Print JSON Responses

Add `| jq` to pretty print JSON responses:

```bash
curl -X GET "${API_URL}/health" | jq
```

```bash
curl -X POST "${API_URL}/algorithm/run" \
  -H "Content-Type: application/json" \
  -d @algorithm_config.json \
  | jq
```

---

## Verbose Mode

Add `-v` flag to see full request/response headers:

```bash
curl -v -X GET "${API_URL}/health"
```

---

## Common Issues

### Connection Refused
If you get "Connection refused":
```bash
# Make sure the API server is running:
cd /home/rio/wrk/proj/fleet-backend
python src/endpoints.py
```

### File Not Found
If CSV files are not found, use absolute paths:
```bash
curl -X POST "${API_URL}/upload/import" \
  -F "locations=@/home/rio/wrk/proj/fleet-backend/data/locations.csv" \
  -F "locations_relations=@/home/rio/wrk/proj/fleet-backend/data/locations_relations.csv" \
  -F "routes=@/home/rio/wrk/proj/fleet-backend/data/routes.csv" \
  -F "segments=@/home/rio/wrk/proj/fleet-backend/data/segments.csv" \
  -F "vehicles=@/home/rio/wrk/proj/fleet-backend/data/vehicles.csv"
```

### Invalid JSON
Make sure your JSON config has all required fields. Use the structure from `algorithm_config.json` as a template.

---

## Quick Test Script

Save this as `test_all_endpoints.sh`:

```bash
#!/bin/bash

API_URL="http://localhost:8000"

echo "=== Testing Root Endpoint ==="
curl -s "${API_URL}/" | jq

echo -e "\n=== Testing Health Check ==="
curl -s "${API_URL}/health" | jq

echo -e "\n=== Testing Database Info ==="
curl -s "${API_URL}/db/info" | jq

echo -e "\n=== Testing Full Optimization ==="
curl -s -X POST "${API_URL}/algorithm/run" \
  -H "Content-Type: application/json" \
  -d @algorithm_config.json | jq
```

Make it executable and run:
```bash
chmod +x test_all_endpoints.sh
./test_all_endpoints.sh
```

