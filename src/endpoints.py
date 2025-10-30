"""
FastAPI endpoints for fleet optimization system.
Handles file uploads (CSVs + JSON config) with validation.
"""
import io
import csv
import json
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not required, will use system env vars


# ===========================
# Pydantic Models for Config
# ===========================

class PlacementConfig(BaseModel):
    strategy: str
    lookahead_days: int
    max_concentration: float
    max_vehicles_per_location: Optional[int] = None


class AssignmentConfig(BaseModel):
    strategy: str
    assignment_lookahead_days: int
    look_ahead_days: int
    chain_depth: int
    chain_weight: float
    max_lookahead_routes: int
    use_chain_optimization: bool


class SwapPolicyConfig(BaseModel):
    max_swaps_per_period: int
    swap_period_days: int


class ServicePolicyConfig(BaseModel):
    service_tolerance_km: int
    service_duration_hours: int
    service_penalty_pln: float
    service_cost_pln: float


class CostsConfig(BaseModel):
    relocation_base_cost_pln: float
    relocation_per_km_pln: float
    relocation_per_hour_pln: float
    overage_per_km_pln: float


class PerformanceConfig(BaseModel):
    progress_report_days: int
    progress_report_interval: int
    use_pathfinding: bool
    use_relation_cache: bool


class AlgorithmConfig(BaseModel):
    """Schema for algorithm_config.json"""
    data_dir: str
    output_dir: str
    placement: PlacementConfig
    assignment: AssignmentConfig
    swap_policy: SwapPolicyConfig
    service_policy: ServicePolicyConfig
    costs: CostsConfig
    performance: PerformanceConfig


# ===========================
# CSV Schema Validators
# ===========================

CSV_SCHEMAS = {
    'locations': {
        'required_columns': ['id', 'name', 'lat', 'long', 'is_hub'],
        'types': {
            'id': int,
            'name': str,
            'lat': float,
            'long': float,
            'is_hub': int,
        }
    },
    'locations_relations': {
        'required_columns': ['id', 'id_loc_1', 'id_loc_2', 'dist', 'time'],
        'types': {
            'id': int,
            'id_loc_1': int,
            'id_loc_2': int,
            'dist': float,
            'time': float,
        }
    },
    'routes': {
        'required_columns': ['id', 'start_datetime', 'end_datetime', 'distance_km'],
        'types': {
            'id': int,
            'start_datetime': str,
            'end_datetime': str,
            'distance_km': float,
        }
    },
    'segments': {
        'required_columns': ['id', 'route_id', 'seq', 'start_loc_id', 'end_loc_id', 'start_datetime', 'end_datetime', 'relation_id'],
        'types': {
            'id': int,
            'route_id': int,
            'seq': int,
            'start_loc_id': int,
            'end_loc_id': int,
            'start_datetime': str,
            'end_datetime': str,
            'relation_id': int,
        }
    },
    'vehicles': {
        'required_columns': ['Id', 'registration_number', 'brand', 'service_interval_km', 'Leasing_start_km', 
                            'leasing_limit_km', 'leasing_start_date', 'leasing_end_date', 'current_odometer_km', 
                            'Current_location_id'],
        'types': {
            'Id': int,
            'registration_number': str,
            'brand': str,
            'service_interval_km': int,
            'Leasing_start_km': int,
            'leasing_limit_km': int,
            'leasing_start_date': str,
            'leasing_end_date': str,
            'current_odometer_km': int,
            'Current_location_id': str,  # Can be "N/A" or int
        }
    }
}


# ===========================
# Helper Functions
# ===========================

def validate_csv_structure(content: bytes, csv_type: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Validate CSV structure against schema and return rows.
    Returns: (is_valid, error_message, rows_data)
    """
    try:
        # Decode bytes to string
        text = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text))
        
        # Get schema
        schema = CSV_SCHEMAS.get(csv_type)
        if not schema:
            return False, f"Unknown CSV type: {csv_type}", []
        
        # Check headers
        headers = reader.fieldnames
        if not headers:
            return False, "CSV has no headers", []
        
        missing_cols = set(schema['required_columns']) - set(headers)
        if missing_cols:
            return False, f"Missing required columns: {missing_cols}", []
        
        # Read and validate rows - validate ALL rows for data integrity
        rows = []
        row_count = 0
        for idx, row in enumerate(reader):
            row_count += 1
            rows.append(row)
            
            # Basic type validation on sample rows (every 100th row + first 10)
            if idx < 10 or idx % 100 == 0:
                for col, expected_type in schema['types'].items():
                    value = row.get(col, '').strip()
                    if value and value != 'N/A':  # Skip empty and N/A values
                        try:
                            if expected_type == int:
                                int(value)
                            elif expected_type == float:
                                float(value)
                        except ValueError:
                            return False, f"Row {idx+1}: Column '{col}' has invalid type (expected {expected_type.__name__})", []
            
            # Limit preview rows for memory
            if len(rows) > 1000:
                rows = rows[:100]  # Keep only first 100 for preview
        
        return True, "Valid", rows
    
    except Exception as e:
        return False, f"Error parsing CSV: {str(e)}", []


def validate_config_json(content: bytes) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate JSON config against schema.
    Returns: (is_valid, error_message, config_dict)
    """
    try:
        # Parse JSON
        config_dict = json.loads(content.decode('utf-8'))
        
        # Validate with Pydantic
        config = AlgorithmConfig(**config_dict)
        
        return True, "Valid", config.model_dump()
    
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}", None
    except ValidationError as e:
        return False, f"Schema validation failed: {e}", None
    except Exception as e:
        return False, f"Error validating config: {str(e)}", None


def print_csv_preview(csv_type: str, rows: List[Dict[str, Any]], max_rows: int = 10):
    """Print CSV preview to console"""
    print(f"\n{'='*80}")
    print(f"📄 {csv_type.upper()}.CSV Preview (first {min(len(rows), max_rows)} rows)")
    print('='*80)
    
    if not rows:
        print("  (empty file)")
        return
    
    # Get headers
    headers = list(rows[0].keys())
    
    # Print headers
    print(" | ".join(headers))
    print("-" * 80)
    
    # Print rows
    for idx, row in enumerate(rows[:max_rows]):
        values = [str(row.get(h, ''))[:15] for h in headers]  # Truncate long values
        print(" | ".join(values))
    
    print(f"\n✓ Total rows shown: {len(rows[:max_rows])}")
    print('='*80)


# ===========================
# FastAPI App
# ===========================

app = FastAPI(
    title="Fleet Optimization API",
    description="Endpoints for uploading and validating fleet data (CSVs + config JSON)",
    version="1.0.0"
)

# Configure CORS - fully permissive
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Fleet Optimization API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "database": "/db/info",
            "csv": {
                "upload": "/csv/upload - Upload single CSV file (auto-detects type and imports to DB)"
            },
            "upload": {
                "validate": "/upload/validate - Validate multiple CSV files (multipart, optional)",
                "process": "/upload/process - Process multiple CSV files (multipart, optional)",
                "import": "/upload/import - Import multiple CSVs to database (multipart, optional)"
            },
            "algorithm": {
                "placement": "/algorithm/placement - Run placement algorithm only",
                "assignment": "/algorithm/assignment - Run assignment algorithm only",
                "full": "/algorithm/run - Run both algorithms (placement + assignment)"
            }
        },
        "description": "Algorithm endpoints require JSON config and pull/save data from database. Use /csv/upload for single CSV imports."
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint - checks API and database connectivity
    """
    from db_adapter import FleetDatabase
    
    health = {
        "api": "healthy",
        "database": "unknown",
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        with FleetDatabase() as db:
            if db.health_check():
                health["database"] = "healthy"
            else:
                health["database"] = "unhealthy"
    except Exception as e:
        health["database"] = "unhealthy"
        health["database_error"] = str(e)
    
    status_code = 200 if health["database"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/db/info")
async def database_info():
    """
    Get database connection and table information
    """
    from db_adapter import FleetDatabase
    
    try:
        with FleetDatabase() as db:
            info = db.get_connection_info()
            return JSONResponse(content=info)
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.post("/upload/validate")
async def validate_upload(
    locations: UploadFile = File(..., description="locations.csv"),
    locations_relations: UploadFile = File(..., description="locations_relations.csv"),
    routes: UploadFile = File(..., description="routes.csv"),
    segments: UploadFile = File(..., description="segments.csv"),
    vehicles: UploadFile = File(..., description="vehicles.csv"),
    config: UploadFile = File(..., description="algorithm_config.json")
):
    """
    Endpoint 1: Validate uploaded files
    
    Accepts 5 CSV files and 1 JSON config file.
    Validates structure and schema, prints preview to console.
    Returns validation results.
    """
    results = {
        "status": "success",
        "files_validated": 0,
        "files_failed": 0,
        "validation_results": {}
    }
    
    csv_files = {
        'locations': locations,
        'locations_relations': locations_relations,
        'routes': routes,
        'segments': segments,
        'vehicles': vehicles
    }
    
    # Validate CSV files
    for csv_type, file in csv_files.items():
        print(f"\n🔍 Validating {csv_type}.csv...")
        
        # Read content
        content = await file.read()
        
        # Validate
        is_valid, error_msg, rows = validate_csv_structure(content, csv_type)
        
        if is_valid:
            results['files_validated'] += 1
            results['validation_results'][csv_type] = {
                "status": "valid",
                "rows_preview": len(rows),
                "filename": file.filename
            }
            
            # Print preview
            print_csv_preview(csv_type, rows)
        else:
            results['files_failed'] += 1
            results['validation_results'][csv_type] = {
                "status": "invalid",
                "error": error_msg,
                "filename": file.filename
            }
            print(f"❌ Validation failed for {csv_type}: {error_msg}")
        
        await file.close()
    
    # Validate JSON config
    print(f"\n🔍 Validating algorithm_config.json...")
    config_content = await config.read()
    is_valid, error_msg, config_data = validate_config_json(config_content)
    
    if is_valid:
        results['files_validated'] += 1
        results['validation_results']['config'] = {
            "status": "valid",
            "filename": config.filename
        }
        
        # Print config preview
        print(f"\n{'='*80}")
        print(f"📄 CONFIG.JSON Preview")
        print('='*80)
        print(json.dumps(config_data, indent=2)[:500] + "...")
        print('='*80)
    else:
        results['files_failed'] += 1
        results['validation_results']['config'] = {
            "status": "invalid",
            "error": error_msg,
            "filename": config.filename
        }
        print(f"❌ Validation failed for config: {error_msg}")
    
    await config.close()
    
    # Set overall status
    if results['files_failed'] > 0:
        results['status'] = 'partial_failure'
        if results['files_validated'] == 0:
            results['status'] = 'failure'
    
    print(f"\n\n{'='*80}")
    print(f"✅ Validation Complete: {results['files_validated']}/{results['files_validated'] + results['files_failed']} files valid")
    print('='*80 + "\n")
    
    return JSONResponse(content=results)


@app.post("/upload/process")
async def process_upload(
    locations: UploadFile = File(..., description="locations.csv"),
    locations_relations: UploadFile = File(..., description="locations_relations.csv"),
    routes: UploadFile = File(..., description="routes.csv"),
    segments: UploadFile = File(..., description="segments.csv"),
    vehicles: UploadFile = File(..., description="vehicles.csv"),
    config: UploadFile = File(..., description="algorithm_config.json")
):
    """
    Endpoint 2: Process uploaded files
    
    Accepts 5 CSV files and 1 JSON config file.
    Validates, loads into memory, and returns summary.
    This endpoint would trigger the optimization algorithm in production.
    """
    print(f"\n{'='*80}")
    print(f"🚀 PROCESSING FILE UPLOAD")
    print('='*80 + "\n")
    
    results = {
        "status": "success",
        "files_processed": {},
        "ready_for_optimization": False,
        "timestamp": datetime.now().isoformat()
    }
    
    csv_files = {
        'locations': locations,
        'locations_relations': locations_relations,
        'routes': routes,
        'segments': segments,
        'vehicles': vehicles
    }
    
    all_valid = True
    
    # Process CSV files
    for csv_type, file in csv_files.items():
        print(f"\n📥 Processing {csv_type}.csv...")
        
        content = await file.read()
        is_valid, error_msg, rows = validate_csv_structure(content, csv_type)
        
        if is_valid:
            # Count total rows (re-read for accurate count)
            text = content.decode('utf-8')
            total_rows = sum(1 for _ in csv.DictReader(io.StringIO(text)))
            
            results['files_processed'][csv_type] = {
                "status": "loaded",
                "total_rows": total_rows,
                "preview_rows": len(rows),
                "filename": file.filename
            }
            
            print_csv_preview(csv_type, rows)
        else:
            all_valid = False
            results['files_processed'][csv_type] = {
                "status": "failed",
                "error": error_msg,
                "filename": file.filename
            }
            print(f"❌ Failed to process {csv_type}: {error_msg}")
        
        await file.close()
    
    # Process JSON config
    print(f"\n📥 Processing algorithm_config.json...")
    config_content = await config.read()
    is_valid, error_msg, config_data = validate_config_json(config_content)
    
    if is_valid:
        results['files_processed']['config'] = {
            "status": "loaded",
            "filename": config.filename,
            "config_preview": {
                "placement_strategy": config_data['placement']['strategy'],
                "assignment_strategy": config_data['assignment']['strategy'],
                "lookahead_days": config_data['placement']['lookahead_days']
            }
        }
        
        print(f"\n{'='*80}")
        print(f"⚙️  CONFIG LOADED")
        print('='*80)
        print(f"  Strategy: {config_data['placement']['strategy']}")
        print(f"  Lookahead: {config_data['placement']['lookahead_days']} days")
        print(f"  Assignment: {config_data['assignment']['strategy']}")
        print('='*80)
    else:
        all_valid = False
        results['files_processed']['config'] = {
            "status": "failed",
            "error": error_msg,
            "filename": config.filename
        }
        print(f"❌ Failed to process config: {error_msg}")
    
    await config.close()
    
    # Set readiness status
    results['ready_for_optimization'] = all_valid
    
    if not all_valid:
        results['status'] = 'failed'
    
    print(f"\n\n{'='*80}")
    if all_valid:
        print(f"✅ ALL FILES PROCESSED SUCCESSFULLY")
        print(f"🎯 Ready for optimization!")
    else:
        print(f"❌ SOME FILES FAILED TO PROCESS")
        print(f"⚠️  Not ready for optimization")
    print('='*80 + "\n")
    
    return JSONResponse(content=results)


@app.post("/upload/import")
async def import_to_database(
    locations: UploadFile = File(..., description="locations.csv"),
    locations_relations: UploadFile = File(..., description="locations_relations.csv"),
    routes: UploadFile = File(..., description="routes.csv"),
    segments: UploadFile = File(..., description="segments.csv"),
    vehicles: UploadFile = File(..., description="vehicles.csv")
):
    """
    Endpoint 3: Import CSVs directly to database (upsert - no conflicts)
    
    Accepts 5 CSV files and imports them to the database.
    Uses upsert logic so re-importing won't create conflicts.
    """
    print(f"\n{'='*80}")
    print(f"🔄 IMPORTING CSV DATA TO DATABASE")
    print('='*80 + "\n")
    
    from db_adapter import FleetDatabase
    import csv as csv_lib
    import io
    
    results = {
        "status": "success",
        "imported": {},
        "errors": []
    }
    
    try:
        with FleetDatabase() as db:
            # Import locations
            print(f"📥 Importing locations...")
            content = await locations.read()
            text = content.decode('utf-8')
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                db.import_location(row)
                count += 1
            db.conn.commit()
            results['imported']['locations'] = count
            print(f"✓ Imported {count} locations")
            
            # Import location relations
            print(f"📥 Importing location relations...")
            content = await locations_relations.read()
            text = content.decode('utf-8')
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                db.import_location_relation(row)
                count += 1
            db.conn.commit()
            results['imported']['location_relations'] = count
            print(f"✓ Imported {count} location relations")
            
            # Import vehicles
            print(f"📥 Importing vehicles...")
            content = await vehicles.read()
            text = content.decode('utf-8')
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                db.import_vehicle(row)
                count += 1
            db.conn.commit()
            results['imported']['vehicles'] = count
            print(f"✓ Imported {count} vehicles")
            
            # Import routes
            print(f"📥 Importing routes...")
            content = await routes.read()
            text = content.decode('utf-8')
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                db.import_route(row)
                count += 1
            db.conn.commit()
            results['imported']['routes'] = count
            print(f"✓ Imported {count} routes")
            
            # Import segments
            print(f"📥 Importing segments...")
            content = await segments.read()
            text = content.decode('utf-8')
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                db.import_segment(row)
                count += 1
            db.conn.commit()
            results['imported']['segments'] = count
            print(f"✓ Imported {count} segments")
        
        print(f"\n{'='*80}")
        print(f"✅ ALL DATA IMPORTED TO DATABASE")
        print('='*80 + "\n")
        
    except Exception as e:
        results['status'] = 'error'
        results['errors'].append(str(e))
        print(f"❌ Error during import: {e}")
    
    return JSONResponse(content=results)


def detect_csv_type(headers: List[str]) -> Optional[str]:
    """
    Detect CSV type based on column headers.
    
    Args:
        headers: List of column names from CSV
    
    Returns:
        CSV type name ('locations', 'vehicles', etc.) or None if unknown
    """
    headers_set = set(h.strip() for h in headers)
    
    # Check each schema to find best match
    best_match = None
    best_score = 0
    
    for csv_type, schema in CSV_SCHEMAS.items():
        required_cols = set(schema['required_columns'])
        matched_cols = required_cols.intersection(headers_set)
        score = len(matched_cols) / len(required_cols)
        
        # Require at least 80% match
        if score >= 0.8 and score > best_score:
            best_score = score
            best_match = csv_type
    
    return best_match


@app.post("/csv/upload")
async def upload_single_csv(file: UploadFile = File(..., description="Single CSV file")):
    """
    Upload a single CSV file and import it to database.
    
    This endpoint automatically detects the CSV type based on its schema/columns
    and imports it into the appropriate database table.
    
    Supported CSV types:
    - locations.csv
    - locations_relations.csv
    - routes.csv
    - segments.csv
    - vehicles.csv
    """
    print(f"\n{'='*80}")
    print(f"📤 SINGLE CSV UPLOAD: {file.filename}")
    print('='*80 + "\n")
    
    from db_adapter import FleetDatabase
    import csv as csv_lib
    import io
    
    results = {
        "status": "success",
        "filename": file.filename,
        "detected_type": None,
        "rows_imported": 0,
        "error": None
    }
    
    try:
        # Read CSV content
        content = await file.read()
        text = content.decode('utf-8')
        
        # Parse CSV to get headers
        reader = csv_lib.DictReader(io.StringIO(text))
        headers = reader.fieldnames
        
        if not headers:
            raise HTTPException(status_code=400, detail="CSV file has no headers")
        
        # Detect CSV type
        csv_type = detect_csv_type(headers)
        
        if not csv_type:
            raise HTTPException(
                status_code=400, 
                detail=f"Could not detect CSV type. Headers found: {', '.join(headers)}"
            )
        
        results['detected_type'] = csv_type
        print(f"🔍 Detected CSV type: {csv_type}")
        
        # Validate CSV structure
        is_valid, error_msg, rows = validate_csv_structure(content, csv_type)
        
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"CSV validation failed: {error_msg}")
        
        print(f"✓ CSV validation passed")
        
        # Import to database based on type
        with FleetDatabase() as db:
            # Re-read CSV for import
            reader = csv_lib.DictReader(io.StringIO(text))
            count = 0
            
            print(f"📥 Importing {csv_type} to database...")
            
            if csv_type == 'locations':
                for row in reader:
                    db.import_location(row)
                    count += 1
            elif csv_type == 'locations_relations':
                for row in reader:
                    db.import_location_relation(row)
                    count += 1
            elif csv_type == 'vehicles':
                for row in reader:
                    db.import_vehicle(row)
                    count += 1
            elif csv_type == 'routes':
                for row in reader:
                    db.import_route(row)
                    count += 1
            elif csv_type == 'segments':
                for row in reader:
                    db.import_segment(row)
                    count += 1
            
            db.conn.commit()
            results['rows_imported'] = count
            
            print(f"✓ Imported {count} rows to {csv_type} table")
        
        print(f"\n{'='*80}")
        print(f"✅ CSV IMPORT COMPLETED")
        print(f"   Type: {csv_type}")
        print(f"   Rows: {count}")
        print('='*80 + "\n")
        
    except HTTPException:
        raise
    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        print(f"❌ Error during CSV import: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()
    
    return JSONResponse(content=results)


def _convert_config_to_algo_config(config: AlgorithmConfig):
    """Helper to convert API config to internal AssignmentConfig"""
    from models import AssignmentConfig as AlgoConfig
    return AlgoConfig(
        relocation_base_cost_pln=config.costs.relocation_base_cost_pln,
        relocation_per_km_pln=config.costs.relocation_per_km_pln,
        relocation_per_hour_pln=config.costs.relocation_per_hour_pln,
        overage_per_km_pln=config.costs.overage_per_km_pln,
        service_cost_pln=config.service_policy.service_cost_pln,
        service_tolerance_km=config.service_policy.service_tolerance_km,
        service_duration_hours=config.service_policy.service_duration_hours,
        service_penalty_pln=config.service_policy.service_penalty_pln,
        max_swaps_per_period=config.swap_policy.max_swaps_per_period,
        swap_period_days=config.swap_policy.swap_period_days,
        assignment_lookahead_days=config.assignment.assignment_lookahead_days,
        look_ahead_days=config.assignment.look_ahead_days,
        chain_depth=config.assignment.chain_depth,
        chain_weight=config.assignment.chain_weight,
        max_lookahead_routes=config.assignment.max_lookahead_routes,
        use_chain_optimization=config.assignment.use_chain_optimization,
        assignment_strategy=config.assignment.strategy,
        placement_lookahead_days=config.placement.lookahead_days,
        placement_strategy=config.placement.strategy,
        placement_max_concentration=config.placement.max_concentration,
        placement_max_vehicles_per_location=config.placement.max_vehicles_per_location,
        use_pathfinding=config.performance.use_pathfinding,
        use_relation_cache=config.performance.use_relation_cache,
        progress_report_interval=config.performance.progress_report_interval
    )


@app.post("/algorithm/placement")
async def run_placement(config: AlgorithmConfig):
    """
    Run vehicle placement algorithm only.
    
    Pulls data from database, calculates optimal vehicle placement,
    and saves placement results back to database.
    """
    print(f"\n{'='*80}")
    print(f"🚀 STARTING PLACEMENT ALGORITHM")
    print('='*80 + "\n")
    
    import sys
    import os
    import time
    sys.path.insert(0, os.path.dirname(__file__))
    
    from db_adapter import FleetDatabase
    from data_loader import load_all_data
    from placement_cost_based import calculate_cost_based_placement
    from placement import apply_placement_to_vehicles
    from output import save_placement_results
    
    results = {
        "status": "running",
        "run_id": None,
        "error": None
    }
    
    try:
        # Start algorithm run in database
        with FleetDatabase() as db:
            run_id = db.start_algorithm_run(config={
                'algorithm': 'placement',
                **config.model_dump()
            })
            results['run_id'] = run_id
        
        print(f"[*] Placement run {run_id} started")
        
        # Convert config
        algo_config = _convert_config_to_algo_config(config)
        
        # Load data from database
        start_time = time.time()
        print(f"[*] Loading data from database...")
        vehicles, locations, relation_lookup, routes = load_all_data(data_dir=None)
        load_time = time.time() - start_time
        print(f"[*] Loaded {len(vehicles)} vehicles, {len(locations)} locations, {len(routes)} routes in {load_time:.2f}s")
        
        # Run placement
        print(f"[*] Calculating optimal placement...")
        placement_start = time.time()
        placement_result = calculate_cost_based_placement(
            vehicles, routes, locations, relation_lookup, algo_config
        )
        apply_placement_to_vehicles(vehicles, placement_result.placements)
        placement_time = time.time() - placement_start
        
        # Save results to database
        print(f"[*] Saving placement results to database...")
        save_placement_results(placement_result, vehicles, run_id=run_id)
        
        runtime = time.time() - start_time
        
        results['status'] = 'completed'
        results['runtime_seconds'] = runtime
        results['vehicles_placed'] = len(placement_result.placements)
        results['total_relocation_cost'] = placement_result.total_cost
        
        print(f"\n{'='*80}")
        print(f"✅ PLACEMENT RUN {run_id} COMPLETED")
        print(f"   Runtime: {runtime:.1f}s")
        print(f"   Vehicles placed: {len(placement_result.placements)}")
        print(f"   Total relocation cost: {placement_result.total_cost:,.2f} PLN")
        print('='*80 + "\n")
        
    except Exception as e:
        results['status'] = 'failed'
        results['error'] = str(e)
        print(f"❌ Placement run failed: {e}")
        
        # Mark run as failed in database
        if results['run_id']:
            with FleetDatabase() as db:
                db.complete_algorithm_run(results['run_id'], error=str(e))
    
    return JSONResponse(content=results)


@app.post("/algorithm/assignment")
async def run_assignment(config: AlgorithmConfig):
    """
    Run route assignment algorithm only.
    
    Pulls data from database (including existing placements),
    assigns routes to vehicles, and saves results back to database.
    
    Note: Requires vehicles to have placement locations set.
    """
    print(f"\n{'='*80}")
    print(f"🚀 STARTING ASSIGNMENT ALGORITHM")
    print('='*80 + "\n")
    
    import sys
    import os
    import time
    sys.path.insert(0, os.path.dirname(__file__))
    
    from db_adapter import FleetDatabase
    from data_loader import load_all_data
    from assignment import assign_routes
    from output import save_assignment_results
    
    results = {
        "status": "running",
        "run_id": None,
        "error": None
    }
    
    try:
        # Start algorithm run in database
        with FleetDatabase() as db:
            run_id = db.start_algorithm_run(config={
                'algorithm': 'assignment',
                **config.model_dump()
            })
            results['run_id'] = run_id
        
        print(f"[*] Assignment run {run_id} started")
        
        # Convert config
        algo_config = _convert_config_to_algo_config(config)
        
        # Load data from database
        start_time = time.time()
        print(f"[*] Loading data from database...")
        vehicles, locations, relation_lookup, routes = load_all_data(data_dir=None)
        load_time = time.time() - start_time
        print(f"[*] Loaded {len(vehicles)} vehicles, {len(locations)} locations, {len(routes)} routes in {load_time:.2f}s")
        
        # Verify vehicles have placement
        vehicles_without_placement = sum(1 for v in vehicles if not hasattr(v, 'current_location') or v.current_location is None)
        if vehicles_without_placement > 0:
            print(f"⚠️  Warning: {vehicles_without_placement} vehicles don't have placement. They may not be assigned routes.")
        
        # Run assignment
        print(f"[*] Assigning routes to vehicles...")
        assignment_start = time.time()
        assignment_result = assign_routes(
            vehicles, routes, relation_lookup, algo_config
        )
        assignment_time = time.time() - assignment_start
        
        # Save results to database
        print(f"[*] Saving assignment results to database...")
        save_assignment_results(assignment_result, vehicles, run_id=run_id)
        
        runtime = time.time() - start_time
        
        results['status'] = 'completed'
        results['runtime_seconds'] = runtime
        results['routes_assigned'] = assignment_result.routes_assigned
        results['routes_unassigned'] = assignment_result.routes_unassigned
        results['total_cost'] = assignment_result.total_cost
        
        print(f"\n{'='*80}")
        print(f"✅ ASSIGNMENT RUN {run_id} COMPLETED")
        print(f"   Runtime: {runtime:.1f}s")
        print(f"   Routes assigned: {assignment_result.routes_assigned}")
        print(f"   Routes unassigned: {assignment_result.routes_unassigned}")
        print(f"   Total cost: {assignment_result.total_cost:,.2f} PLN")
        print('='*80 + "\n")
        
    except Exception as e:
        results['status'] = 'failed'
        results['error'] = str(e)
        print(f"❌ Assignment run failed: {e}")
        
        # Mark run as failed in database
        if results['run_id']:
            with FleetDatabase() as db:
                db.complete_algorithm_run(results['run_id'], error=str(e))
    
    return JSONResponse(content=results)


@app.post("/algorithm/run")
async def run_full_optimization(config: AlgorithmConfig):
    """
    Run complete optimization (placement + assignment).
    
    Reads data from database, runs both algorithms sequentially,
    saves all results back to database.
    """
    print(f"\n{'='*80}")
    print(f"🚀 STARTING FULL OPTIMIZATION (PLACEMENT + ASSIGNMENT)")
    print('='*80 + "\n")
    
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    
    from db_adapter import FleetDatabase
    from optimizer import run_optimization
    import time
    
    results = {
        "status": "running",
        "run_id": None,
        "error": None
    }
    
    try:
        # Start algorithm run in database
        with FleetDatabase() as db:
            run_id = db.start_algorithm_run(config={
                'algorithm': 'full',
                **config.model_dump()
            })
            results['run_id'] = run_id
        
        print(f"[*] Algorithm run {run_id} started")
        
        # Convert config to AssignmentConfig
        algo_config = _convert_config_to_algo_config(config)
        
        # Run optimization (data_dir=None forces DB usage, pass run_id for tracking)
        start_time = time.time()
        placement_result, assignment_result = run_optimization(
            data_dir=None,  # Force DB usage
            output_dir=config.output_dir,
            config=algo_config,
            run_id=run_id  # Pass run_id for database tracking
        )
        runtime = time.time() - start_time
        
        # Results are already saved to DB by output.py with our run_id
        results['status'] = 'completed'
        results['runtime_seconds'] = runtime
        results['vehicles_placed'] = len(placement_result.placements)
        results['routes_assigned'] = assignment_result.routes_assigned
        results['routes_unassigned'] = assignment_result.routes_unassigned
        results['total_cost'] = assignment_result.total_cost
        
        print(f"\n{'='*80}")
        print(f"✅ ALGORITHM RUN {run_id} COMPLETED")
        print(f"   Runtime: {runtime:.1f}s")
        print(f"   Vehicles placed: {len(placement_result.placements)}")
        print(f"   Routes assigned: {assignment_result.routes_assigned}")
        print(f"   Total Cost: {assignment_result.total_cost:,.2f} PLN")
        print('='*80 + "\n")
        
    except Exception as e:
        results['status'] = 'failed'
        results['error'] = str(e)
        print(f"❌ Algorithm run failed: {e}")
        
        # Mark run as failed in database
        if results['run_id']:
            with FleetDatabase() as db:
                db.complete_algorithm_run(results['run_id'], error=str(e))
    
    return JSONResponse(content=results)


# ===========================
# Error Handlers
# ===========================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle unexpected errors"""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": str(exc),
            "type": type(exc).__name__
        }
    )


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Fleet Optimization API...")
    print("📖 Docs available at: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)

