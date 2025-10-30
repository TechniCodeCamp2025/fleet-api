# 🚀 Quick Start - Fleet Optimization API

## TL;DR

```bash
# 1. Install dependencies
pip install fastapi uvicorn pydantic python-multipart

# 2. Start the API
python src/endpoints.py

# 3. Open in browser
# http://localhost:8000/docs

# 4. Test it
python test_api.py
```

## What You Get

### ✅ 2 Endpoints Created

1. **`POST /upload/validate`** - Validates files and schemas
2. **`POST /upload/process`** - Processes and loads files into memory

Both endpoints accept **6 files** via multipart form-data:
- `locations` → locations.csv
- `locations_relations` → locations_relations.csv  
- `routes` → routes.csv
- `segments` → segments.csv
- `vehicles` → vehicles.csv
- `config` → algorithm_config.json

### ✅ Features

- **Schema Validation**: All CSV columns and JSON config validated
- **Type Checking**: Data types verified (int, float, str, datetime)
- **Console Preview**: First 10 rows of each CSV printed to terminal
- **Error Messages**: Clear validation errors with specific details
- **Interactive Docs**: Auto-generated Swagger UI at `/docs`

### ✅ Files Created

```
fleet-backend/
├── src/
│   ├── endpoints.py         # Main FastAPI app with 2 endpoints ⭐
│   └── endpoint_csv.py      # CSV utility functions
├── API_README.md            # Detailed API documentation
├── QUICKSTART_API.md        # This file
├── test_api.py              # Automated test script
└── run_api.sh               # Quick start script
```

## Examples

### Using Swagger UI (Easiest)

1. Start API: `python src/endpoints.py`
2. Go to: http://localhost:8000/docs
3. Click "Try it out" on any endpoint
4. Upload your files
5. Click "Execute"
6. Check your terminal for CSV previews!

### Using curl

```bash
curl -X POST "http://localhost:8000/upload/validate" \
  -F "locations=@data/locations.csv" \
  -F "locations_relations=@data/locations_relations.csv" \
  -F "routes=@data/routes.csv" \
  -F "segments=@data/segments.csv" \
  -F "vehicles=@data/vehicles.csv" \
  -F "config=@algorithm_config.json"
```

### Using Python

```python
import requests

files = {
    'locations': open('data/locations.csv', 'rb'),
    'locations_relations': open('data/locations_relations.csv', 'rb'),
    'routes': open('data/routes.csv', 'rb'),
    'segments': open('data/segments.csv', 'rb'),
    'vehicles': open('data/vehicles.csv', 'rb'),
    'config': open('algorithm_config.json', 'rb'),
}

response = requests.post('http://localhost:8000/upload/validate', files=files)
print(response.json())
```

## Output Example

When you upload files, you'll see in your **terminal**:

```
================================================================================
📄 LOCATIONS.CSV Preview (first 10 rows)
================================================================================
id | name | lat | long | is_hub
--------------------------------------------------------------------------------
1 | LOC-0001 | 53.007467 | 21.843845 | 0
2 | LOC-0002 | 51.399369 | 20.874733 | 0
3 | LOC-0003 | 50.320700 | 22.789254 | 0
...

✓ Total rows shown: 10
================================================================================
```

And in your **API response**:

```json
{
  "status": "success",
  "files_validated": 6,
  "files_failed": 0,
  "validation_results": {
    "locations": {
      "status": "valid",
      "rows_preview": 10,
      "filename": "locations.csv"
    },
    ...
  }
}
```

## Validation

### What's Validated

**CSV Files:**
- ✅ Required column headers present
- ✅ Data types match schema (int, float, str)
- ✅ First 3 rows type-checked
- ✅ Handles "N/A" and empty values

**JSON Config:**
- ✅ All required nested objects present
- ✅ All fields match expected types
- ✅ Uses strict Pydantic validation

### Error Example

If you upload a CSV with missing columns:

```json
{
  "status": "failure",
  "files_validated": 5,
  "files_failed": 1,
  "validation_results": {
    "locations": {
      "status": "invalid",
      "error": "Missing required columns: {'is_hub'}",
      "filename": "bad_locations.csv"
    }
  }
}
```

## Next Steps

1. **Test the endpoints**: `python test_api.py`
2. **Read full docs**: See `API_README.md`
3. **Customize validation**: Edit schemas in `src/endpoints.py`
4. **Add processing logic**: Extend the `/upload/process` endpoint

## Troubleshooting

**Import errors?**
```bash
pip install fastapi uvicorn pydantic python-multipart
```

**Port already in use?**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn src.endpoints:app --port 8001
```

**Files not found?**
Make sure you're running from the project root directory:
```bash
cd /home/rio/wrk/proj/fleet-backend
python src/endpoints.py
```

## Need Help?

- Check logs in terminal where API is running
- Use `/docs` for interactive testing
- Review `API_README.md` for detailed docs
- Examine `src/endpoints.py` for schema definitions

