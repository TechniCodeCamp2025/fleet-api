# CSV Data Upload Guide

This guide explains how to use the `upload_csv_data.py` script to upload CSV files from the `data/` directory to your PostgreSQL database.

## Prerequisites

1. PostgreSQL database with the schema from `schema.sql` already applied
2. Python 3 with `psycopg2` installed
3. CSV files in the `data/` directory:
   - `locations.csv`
   - `locations_relations.csv`
   - `vehicles.csv`
   - `routes.csv`
   - `segments.csv`

## Installation

Install the required Python package:

```bash
pip install psycopg2-binary
```

Or if using `uv`:

```bash
uv pip install psycopg2-binary
```

## Usage

### Basic Usage (using environment variables)

Set your database credentials as environment variables:

```bash
export DB_NAME=fleet_optimization
export DB_USER=fleet_user
export DB_PASSWORD=fleet_password
export DB_HOST=localhost
export DB_PORT=5432

# Run the upload
./upload_csv_data.py
```

### Using Command Line Arguments

You can also specify database credentials directly:

```bash
./upload_csv_data.py \
  --db-name fleet_optimization \
  --db-user fleet_user \
  --db-password fleet_password \
  --db-host localhost \
  --db-port 5432
```

### Specify Custom Data Directory

If your CSV files are in a different location:

```bash
./upload_csv_data.py --data-dir /path/to/csv/files
```

## What the Script Does

The script uploads data in the correct order to respect foreign key dependencies:

1. **Locations** - Physical locations (hubs and endpoints)
2. **Location Relations** - Distance and time between locations
3. **Vehicles** - Fleet vehicles with their current state
4. **Routes** - Routes to be assigned
5. **Segments** - Individual segments within each route

### Features

- **Upsert Logic**: Uses the database upsert functions to insert or update records
- **Progress Indicators**: Shows progress during upload
- **Transaction Safety**: Commits after each table to ensure data integrity
- **Error Handling**: Provides clear error messages if something goes wrong
- **Null Handling**: Correctly handles "N/A" values in CSV files (e.g., for vehicle locations)
- **Distance Calculation**: Automatically fetches segment distances from location_relations

## CSV File Format

### locations.csv
```csv
id,name,lat,long,is_hub
1,LOC-0001,53.007467,21.843845,0
```

### locations_relations.csv
```csv
id,id_loc_1,id_loc_2,dist,time
1,1,4,319.546,335.62
```

### vehicles.csv
```csv
Id,registration_number,brand,service_interval_km,Leasing_start_km,leasing_limit_km,leasing_start_date,leasing_end_date,current_odometer_km,Current_location_id
1,KR5246J,Volvo,110000,0,450000,2021-03-08 00:00:00,2024-03-07 00:00:00,328536,N/A
```

### routes.csv
```csv
id,start_datetime,end_datetime,distance_km
1,2024-01-01 00:00:00,2024-01-01 03:56:39,99.629
```

### segments.csv
```csv
id,route_id,seq,start_loc_id,end_loc_id,start_datetime,end_datetime,relation_id
1,1,1,73,3,2024-01-01 00:00:00,2024-01-01 01:56:45,17638
```

## Example Output

```
======================================================================
Fleet Optimization - CSV Data Upload
======================================================================

Connecting to database...
✓ Connected successfully

Uploading locations from data/locations.csv...
  Processed 100 locations...
  Processed 200 locations...
✓ Uploaded 300 locations

Uploading location relations from data/locations_relations.csv...
  Processed 1000 relations...
  Processed 2000 relations...
✓ Uploaded 29407 location relations

Uploading vehicles from data/vehicles.csv...
  Processed 50 vehicles...
  Processed 100 vehicles...
✓ Uploaded 180 vehicles

Uploading routes from data/routes.csv...
  Processed 5000 routes...
  Processed 10000 routes...
✓ Uploaded 100300 routes

Uploading segments from data/segments.csv...
  Building relation distance cache...
  Processed 10000 segments...
  Processed 20000 segments...
✓ Uploaded 219409 segments

======================================================================
Upload Complete!
======================================================================
  Locations:                 300
  Location Relations:     29,407
  Vehicles:                  180
  Routes:               100,300
  Segments:             219,409
======================================================================
```

## Troubleshooting

### Connection Error

If you get a connection error, verify:
- PostgreSQL is running
- Database credentials are correct
- Database exists and schema is applied

### Missing CSV Files

Ensure all required CSV files are in the `data/` directory (or the directory specified with `--data-dir`).

### Foreign Key Violations

If you see foreign key errors:
- Make sure the schema from `schema.sql` has been applied
- Check that CSV files have valid references (e.g., location IDs in vehicles.csv exist in locations.csv)

### Re-running the Script

The script uses upsert functions, so it's safe to run multiple times. Existing records will be updated with new data.

