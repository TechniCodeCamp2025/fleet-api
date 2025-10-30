# Quick Start - Database Integration

## 🚀 5-Minute Setup

### 1. Install PostgreSQL
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql

# Start service
sudo systemctl start postgresql    # Linux
brew services start postgresql     # macOS
```

### 2. Create Database
```bash
sudo -u postgres createdb fleet
sudo -u postgres psql fleet < schema.sql
```

### 3. Install Python Dependencies
```bash
pip install psycopg2-binary
# or
uv pip install psycopg2-binary
```

### 4. Import Your Data
```bash
export DATABASE_URL="dbname=fleet"

# Start API server
python src/main.py

# In another terminal, import CSVs
curl -X POST http://localhost:8000/upload/import \
  -F "locations=@data/locations.csv" \
  -F "locations_relations=@data/locations_relations.csv" \
  -F "routes=@data/routes.csv" \
  -F "segments=@data/segments.csv" \
  -F "vehicles=@data/vehicles.csv"
```

### 5. Run Optimization
```bash
export DATABASE_URL="dbname=fleet"
python src/run_optimizer.py full
```

## 📊 Check Results

```bash
psql fleet

# View latest run
SELECT id, started_at, completed_at, routes_processed, total_cost_pln 
FROM algorithm_runs 
ORDER BY started_at DESC 
LIMIT 1;

# View assignments
SELECT COUNT(*) FROM assignments;

# View vehicle states
SELECT v.registration_number, vs.odometer_km, vs.km_this_lease_year
FROM vehicle_states vs
JOIN vehicles v ON vs.vehicle_id = v.id
ORDER BY v.registration_number;
```

## 🔄 Running Multiple Times

The system uses **upsert logic** for imports - you can re-import CSVs without conflicts:

```bash
# Re-import updated data
curl -X POST http://localhost:8000/upload/import \
  -F "routes=@data/routes_updated.csv" \
  -F "segments=@data/segments_updated.csv" \
  ...

# Run optimizer again
python src/run_optimizer.py full
```

Each run creates a new `algorithm_runs` record with unique `run_id`.

## 🎯 Two Modes

### Database Mode (Recommended)
```bash
export DATABASE_URL="dbname=fleet"
python src/run_optimizer.py full
# → Reads from database, writes to database
```

### CSV Mode (Legacy/Testing)
```bash
unset DATABASE_URL  # or don't set it
python src/run_optimizer.py full
# → Reads from CSV files, writes to CSV files
```

## 🌐 API Endpoints

With server running (`python src/main.py`):

- `POST /upload/import` - Import CSV files to database
- `POST /algorithm/run` - Run optimization from database
- `POST /upload/validate` - Validate CSV files
- `POST /upload/process` - Process/preview CSV files
- `GET /` - Health check

Interactive docs: http://localhost:8000/docs

## ⚡ Common Commands

```bash
# Check database connection
psql -d fleet -c "SELECT version();"

# View all tables
psql -d fleet -c "\dt"

# Count records
psql -d fleet -c "
  SELECT 'locations' as table, count(*) FROM locations
  UNION ALL SELECT 'vehicles', count(*) FROM vehicles
  UNION ALL SELECT 'routes', count(*) FROM routes;
"

# Reset database (WARNING: deletes all data)
psql -d fleet -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -d fleet < schema.sql
```

## 🔧 Troubleshooting

### "connection refused"
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql   # Linux
brew services list                 # macOS

# Start if needed
sudo systemctl start postgresql
```

### "database does not exist"
```bash
# Create database
sudo -u postgres createdb fleet
```

### "psycopg2 module not found"
```bash
pip install psycopg2-binary
```

### "relation does not exist"
```bash
# Initialize schema
psql -d fleet < schema.sql
```

## 📚 More Information

- **DATABASE_INTEGRATION.md** - Complete integration guide
- **INTEGRATION_SUMMARY.md** - Technical summary of changes
- **schema.sql** - Database schema definition
- **API_README.md** - API documentation

---

**Ready to go!** 🎉

Set `DATABASE_URL` and run `python src/run_optimizer.py full`

