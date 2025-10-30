# Fleet Optimization System - Predictive Fleet Swap AI

Backend system for optimizing fleet vehicle placement and route assignments with predictive swap recommendations.

## 🚀 Quick Start

### Option 1: API Server (Recommended for Testing)

```bash
# Start the FastAPI server
python src/main.py

# Or use the helper script
./run_server.sh
```

Then open `upload_test.html` in your browser to test file uploads!

- **API Docs**: http://localhost:8000/docs
- **Test Interface**: Open `upload_test.html` in browser

### Option 2: CLI Optimization Algorithm

```bash
# Run full optimization
python src/run_optimizer.py full

# Or quick test (uses config lookahead windows)
python src/run_optimizer.py test

# Using helper scripts
./run_full.sh   # Full optimization (takes 15-60 minutes)
./run_test.sh   # Quick test
```

## 📁 Project Structure

```
fleet-backend/
├── src/
│   ├── main.py                  # FastAPI server launcher ⭐
│   ├── run_optimizer.py         # CLI optimization runner
│   ├── endpoints.py             # API endpoints (upload/validate/process)
│   ├── endpoint_csv.py          # CSV utilities
│   ├── models.py                # Data models
│   ├── optimizer.py             # Main optimization engine
│   ├── placement.py             # Vehicle placement algorithm
│   ├── assignment.py            # Route assignment algorithm
│   ├── constraints.py           # Business constraints
│   ├── costs.py                 # Cost calculation
│   ├── pathfinding.py           # Multi-hop routing
│   ├── data_loader.py           # CSV data loading
│   └── output.py                # Results generation
├── data/                        # Input CSV files
├── output/                      # Generated results
├── upload_test.html             # Web UI for testing uploads ⭐
├── algorithm_config.json        # Algorithm configuration
├── API_README.md                # Detailed API documentation
├── QUICKSTART_API.md            # API quick start guide
├── test_api.py                  # API automated tests
└── run_server.sh                # Server launch script
```

## 🌐 API Server

The FastAPI server provides endpoints for uploading and processing fleet data files.

### Start Server

```bash
# Method 1: Direct
python src/main.py

# Method 2: Script
./run_server.sh

# Method 3: Custom port
API_PORT=8080 python src/main.py
```

### Endpoints

- `POST /upload/validate` - Validate uploaded files
- `POST /upload/process` - Validate and process files

### Testing

1. **Web Interface**: Open `upload_test.html` in browser
2. **Python Script**: `python test_api.py`
3. **Interactive Docs**: http://localhost:8000/docs
4. **curl**: See examples in `API_README.md`

## 🔧 Installation

### Python Dependencies

```bash
# Core dependencies (for algorithms)
pip install numpy

# Web dependencies (for API server)
pip install fastapi uvicorn pydantic python-multipart

# Or install all at once
pip install ".[web]"
```

### Data Files Required

Place these CSV files in the `data/` directory:
- `locations.csv` - Location information (300 locations)
- `locations_relations.csv` - Distance/time between locations
- `routes.csv` - Route definitions (100k+ routes)
- `segments.csv` - Route segments
- `vehicles.csv` - Vehicle fleet information (180 vehicles)

Plus: `algorithm_config.json` in project root

## ⚙️ Configuration

Edit `algorithm_config.json` to configure:
- Placement strategy and parameters
- Assignment strategy and lookahead
- Cost parameters (relocation, overage, service)
- Swap policies
- Service policies
- Performance tuning

See `ALGORITHM_SPEC_V2.md` for detailed algorithm documentation.

## 📊 Usage Examples

### API Server Example

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

### CLI Optimization Example

```bash
# Full optimization (all routes)
python src/run_optimizer.py full

# Quick test (using lookahead from config)
python src/run_optimizer.py test

# Results will be in output/ directory
```

## 📈 Output

The system generates several output files:

- `vehicles_placed_{timestamp}.csv` - Initial vehicle placement
- `assignments_{timestamp}.csv` - Route-to-vehicle assignments
- `vehicle_states_{timestamp}.csv` - Final vehicle states
- `summary_{timestamp}.json` - Optimization summary
- `placement_report_{timestamp}.json` - Placement analysis
- `critical_alerts_{timestamp}.json` - Issues and warnings
- `fleet_prediction_summary_{timestamp}.json` - Future predictions

## 🧪 Testing

### Test API
```bash
python test_api.py
```

### Test Algorithms
```bash
python test_placement.py
python test_assignment.py
```

### Quick System Test
```bash
./run_test.sh
```

## 📚 Documentation

- **API_README.md** - Detailed API documentation
- **QUICKSTART_API.md** - Quick API start guide
- **ALGORITHM_SPEC_V2.md** - Algorithm specification
- **API Docs (Interactive)** - http://localhost:8000/docs (when server running)

## 🎯 Key Features

### Placement Algorithm
- Coverage-first strategy
- Hub utilization
- Demand analysis from historical routes
- Concentration limits to avoid clustering

### Assignment Algorithm
- Greedy assignment with optional lookahead
- Swap policy enforcement (max 1 swap per 90 days)
- Service interval tracking
- Overage cost minimization
- Multi-hop pathfinding (optional)

### Cost Optimization
- Relocation costs (base + km + time)
- Overage penalties
- Service costs
- Swap restrictions

### Validation & Constraints
- Annual mileage limits
- Lifetime contract limits
- Service intervals
- Swap windows
- Vehicle availability

## 🔒 Business Rules

- Max 1 relocation per vehicle per 90 days
- Service required at interval + tolerance
- Annual mileage limits enforced
- Relocation costs include base + distance + time
- Overage penalties applied at 0.92 PLN/km

## 🚦 Development

```bash
# Run linter
ruff check src/

# Run tests
pytest

# Format code
ruff format src/
```

## 📝 Notes

- The API server (`src/main.py`) is for uploading/validating files
- The optimization CLI (`src/run_optimizer.py`) runs the actual algorithms
- Full optimization processes 100k+ routes and takes 15-60 minutes
- Test mode uses configurable lookahead windows for faster iteration
- All uploaded files are validated against strict schemas
- Console output shows first 10 rows of each CSV for verification

## 🤝 Contributing

This is a hackathon project for LSP Group. The system implements:
1. **Vehicle Placement** - Strategic initial positioning
2. **Route Assignment** - Cost-optimized vehicle-to-route matching
3. **Predictive Swaps** - Proactive relocation recommendations

## 📄 License

Proprietary - LSP Group Hackathon Project

---

**Quick Commands**
```bash
# Start API server
python src/main.py

# Run optimization
python src/run_optimizer.py full

# Test API
python test_api.py

# View docs
open http://localhost:8000/docs
```
