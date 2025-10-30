#!/usr/bin/env python3
"""
Upload CSV data from data/ directory to PostgreSQL database
Uses batch inserts for maximum performance
"""

import csv
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
import argparse

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Using system environment variables only.")
    print("Install with: pip install python-dotenv")


def get_db_connection(config=None):
    """Establish database connection"""
    if config:
        return psycopg2.connect(**config)
    
    # Try environment variables (loaded from .env if available)
    # Falls back to hardcoded AWS RDS credentials
    conn_params = {
        'dbname': os.getenv('DB_NAME', 'fleet_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'wkt8dmp8nyw!uwf4XUQ'),
        'host': os.getenv('DB_HOST', 'fleetdb.cwni7urg5vil.eu-central-1.rds.amazonaws.com'),
        'port': os.getenv('DB_PORT', '5432')
    }
    
    return psycopg2.connect(**conn_params)


def parse_boolean(value):
    """Parse boolean value from CSV"""
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ('1', 'true', 't', 'yes', 'y'):
            return True
        elif value in ('0', 'false', 'f', 'no', 'n', ''):
            return False
    return bool(int(value))


def parse_nullable_int(value):
    """Parse integer that might be N/A or null"""
    if not value or value.strip().upper() == 'N/A':
        return None
    return int(value.strip())


def upload_locations(cursor, csv_path):
    """Upload locations from CSV using batch insert"""
    print(f"Uploading locations from {csv_path}...")
    
    data = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append((
                int(row['id']),
                row['name'],
                float(row['lat']),
                float(row['long']),
                parse_boolean(row['is_hub'])
            ))
    
    # Batch insert using execute_values (MUCH faster)
    execute_values(
        cursor,
        """
        INSERT INTO locations (id, name, lat, long, is_hub)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            lat = EXCLUDED.lat,
            long = EXCLUDED.long,
            is_hub = EXCLUDED.is_hub
        """,
        data,
        page_size=1000
    )
    
    print(f"✓ Uploaded {len(data)} locations")
    return len(data)


def upload_location_relations(cursor, csv_path):
    """Upload location relations from CSV using batch insert"""
    print(f"Uploading location relations from {csv_path}...")
    
    data = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append((
                int(row['id']),
                int(row['id_loc_1']),
                int(row['id_loc_2']),
                float(row['dist']),
                float(row['time'])
            ))
    
    print(f"  Processing {len(data)} relations in batches...")
    
    # Batch insert
    execute_values(
        cursor,
        """
        INSERT INTO location_relations (id, from_location_id, to_location_id, distance_km, time_minutes)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET from_location_id = EXCLUDED.from_location_id,
            to_location_id = EXCLUDED.to_location_id,
            distance_km = EXCLUDED.distance_km,
            time_minutes = EXCLUDED.time_minutes
        """,
        data,
        page_size=5000
    )
    
    print(f"✓ Uploaded {len(data)} location relations")
    return len(data)


def upload_vehicles(cursor, csv_path):
    """Upload vehicles from CSV using batch insert"""
    print(f"Uploading vehicles from {csv_path}...")
    
    data = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle case-insensitive column names
            vehicle_id = int(row.get('Id') or row.get('id'))
            current_location = parse_nullable_int(
                row.get('Current_location_id') or row.get('current_location_id')
            )
            
            data.append((
                vehicle_id,
                row['registration_number'],
                row['brand'],
                int(row['service_interval_km']),
                int(row.get('Leasing_start_km') or row.get('leasing_start_km')),
                int(row['leasing_limit_km']),
                datetime.strptime(row['leasing_start_date'], '%Y-%m-%d %H:%M:%S'),
                datetime.strptime(row['leasing_end_date'], '%Y-%m-%d %H:%M:%S'),
                int(row['current_odometer_km']),
                current_location
            ))
    
    # Batch insert
    execute_values(
        cursor,
        """
        INSERT INTO vehicles (
            id, registration_number, brand, service_interval_km,
            leasing_start_km, leasing_limit_km, leasing_start_date, leasing_end_date,
            current_odometer_km, current_location_id
        )
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET registration_number = EXCLUDED.registration_number,
            brand = EXCLUDED.brand,
            service_interval_km = EXCLUDED.service_interval_km,
            leasing_start_km = EXCLUDED.leasing_start_km,
            leasing_limit_km = EXCLUDED.leasing_limit_km,
            leasing_start_date = EXCLUDED.leasing_start_date,
            leasing_end_date = EXCLUDED.leasing_end_date,
            current_odometer_km = EXCLUDED.current_odometer_km,
            current_location_id = EXCLUDED.current_location_id,
            updated_at = current_timestamp
        """,
        data,
        page_size=500
    )
    
    print(f"✓ Uploaded {len(data)} vehicles")
    return len(data)


def upload_routes(cursor, csv_path):
    """Upload routes from CSV using batch insert"""
    print(f"Uploading routes from {csv_path}...")
    
    data = []
    batch_size = 10000
    count = 0
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            data.append((
                int(row['id']),
                datetime.strptime(row['start_datetime'], '%Y-%m-%d %H:%M:%S'),
                datetime.strptime(row['end_datetime'], '%Y-%m-%d %H:%M:%S'),
                float(row['distance_km'])
            ))
            
            # Process in batches to avoid memory issues
            if len(data) >= batch_size:
                execute_values(
                    cursor,
                    """
                    INSERT INTO routes (id, start_datetime, end_datetime, distance_km)
                    VALUES %s
                    ON CONFLICT (id) DO UPDATE
                    SET start_datetime = EXCLUDED.start_datetime,
                        end_datetime = EXCLUDED.end_datetime,
                        distance_km = EXCLUDED.distance_km
                    """,
                    data,
                    page_size=5000
                )
                count += len(data)
                print(f"  Processed {count} routes...")
                data = []
        
        # Upload remaining data
        if data:
            execute_values(
                cursor,
                """
                INSERT INTO routes (id, start_datetime, end_datetime, distance_km)
                VALUES %s
                ON CONFLICT (id) DO UPDATE
                SET start_datetime = EXCLUDED.start_datetime,
                    end_datetime = EXCLUDED.end_datetime,
                    distance_km = EXCLUDED.distance_km
                """,
                data,
                page_size=5000
            )
            count += len(data)
    
    print(f"✓ Uploaded {count} routes")
    return count


def upload_segments(cursor, csv_path):
    """Upload segments from CSV using batch insert
    
    Note: Fetches distances from location_relations in bulk
    """
    print(f"Uploading segments from {csv_path}...")
    
    # Build a cache of relation distances
    print("  Building relation distance cache...")
    cursor.execute("SELECT id, distance_km FROM location_relations")
    relation_distances = {row[0]: row[1] for row in cursor.fetchall()}
    print(f"  Cached {len(relation_distances)} relation distances")
    
    data = []
    batch_size = 20000
    count = 0
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            relation_id = int(row['relation_id'])
            distance_km = relation_distances.get(relation_id, 0.0)
            
            data.append((
                int(row['id']),
                int(row['route_id']),
                int(row['seq']),
                int(row['start_loc_id']),
                int(row['end_loc_id']),
                datetime.strptime(row['start_datetime'], '%Y-%m-%d %H:%M:%S'),
                datetime.strptime(row['end_datetime'], '%Y-%m-%d %H:%M:%S'),
                distance_km,
                relation_id
            ))
            
            # Process in batches
            if len(data) >= batch_size:
                execute_values(
                    cursor,
                    """
                    INSERT INTO segments (
                        id, route_id, seq, start_location_id, end_location_id,
                        start_datetime, end_datetime, distance_km, relation_id
                    )
                    VALUES %s
                    ON CONFLICT (id) DO UPDATE
                    SET route_id = EXCLUDED.route_id,
                        seq = EXCLUDED.seq,
                        start_location_id = EXCLUDED.start_location_id,
                        end_location_id = EXCLUDED.end_location_id,
                        start_datetime = EXCLUDED.start_datetime,
                        end_datetime = EXCLUDED.end_datetime,
                        distance_km = EXCLUDED.distance_km,
                        relation_id = EXCLUDED.relation_id
                    """,
                    data,
                    page_size=10000
                )
                count += len(data)
                print(f"  Processed {count} segments...")
                data = []
        
        # Upload remaining data
        if data:
            execute_values(
                cursor,
                """
                INSERT INTO segments (
                    id, route_id, seq, start_location_id, end_location_id,
                    start_datetime, end_datetime, distance_km, relation_id
                )
                VALUES %s
                ON CONFLICT (id) DO UPDATE
                SET route_id = EXCLUDED.route_id,
                    seq = EXCLUDED.seq,
                    start_location_id = EXCLUDED.start_location_id,
                    end_location_id = EXCLUDED.end_location_id,
                    start_datetime = EXCLUDED.start_datetime,
                    end_datetime = EXCLUDED.end_datetime,
                    distance_km = EXCLUDED.distance_km,
                    relation_id = EXCLUDED.relation_id
                """,
                data,
                page_size=10000
            )
            count += len(data)
    
    print(f"✓ Uploaded {count} segments")
    return count


def main():
    parser = argparse.ArgumentParser(
        description='Upload CSV files to Fleet Optimization database (FAST batch mode)'
    )
    parser.add_argument(
        '--data-dir',
        default='data',
        help='Directory containing CSV files (default: data)'
    )
    parser.add_argument(
        '--db-name',
        default=None,
        help='Database name (default: from env or fleet_db)'
    )
    parser.add_argument(
        '--db-user',
        default=None,
        help='Database user (default: from env or postgres)'
    )
    parser.add_argument(
        '--db-password',
        default=None,
        help='Database password (default: from env or hardcoded)'
    )
    parser.add_argument(
        '--db-host',
        default=None,
        help='Database host (default: from env or hardcoded AWS RDS)'
    )
    parser.add_argument(
        '--db-port',
        default=None,
        help='Database port (default: from env or 5432)'
    )
    
    args = parser.parse_args()
    
    # Build connection config
    conn_config = {}
    if args.db_name:
        conn_config['dbname'] = args.db_name
    if args.db_user:
        conn_config['user'] = args.db_user
    if args.db_password:
        conn_config['password'] = args.db_password
    if args.db_host:
        conn_config['host'] = args.db_host
    if args.db_port:
        conn_config['port'] = args.db_port
    
    # File paths
    data_dir = args.data_dir
    files = {
        'locations': os.path.join(data_dir, 'locations.csv'),
        'location_relations': os.path.join(data_dir, 'locations_relations.csv'),
        'vehicles': os.path.join(data_dir, 'vehicles.csv'),
        'routes': os.path.join(data_dir, 'routes.csv'),
        'segments': os.path.join(data_dir, 'segments.csv'),
    }
    
    # Check all files exist
    missing_files = [name for name, path in files.items() if not os.path.exists(path)]
    if missing_files:
        print(f"Error: Missing CSV files: {', '.join(missing_files)}")
        sys.exit(1)
    
    print("=" * 70)
    print("Fleet Optimization - CSV Data Upload (BATCH MODE)")
    print("=" * 70)
    print()
    
    start_time = datetime.now()
    
    try:
        # Connect to database
        print("Connecting to database...")
        conn = get_db_connection(conn_config if conn_config else None)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        print()
        
        # Upload in dependency order
        stats = {}
        
        # 1. Locations (no dependencies)
        stats['locations'] = upload_locations(cursor, files['locations'])
        conn.commit()
        print()
        
        # 2. Location relations (depends on locations)
        stats['location_relations'] = upload_location_relations(
            cursor, files['location_relations']
        )
        conn.commit()
        print()
        
        # 3. Vehicles (depends on locations for current_location_id)
        stats['vehicles'] = upload_vehicles(cursor, files['vehicles'])
        conn.commit()
        print()
        
        # 4. Routes (no dependencies on other data tables)
        stats['routes'] = upload_routes(cursor, files['routes'])
        conn.commit()
        print()
        
        # 5. Segments (depends on routes and location_relations)
        stats['segments'] = upload_segments(cursor, files['segments'])
        conn.commit()
        print()
        
        elapsed = datetime.now() - start_time
        
        # Summary
        print("=" * 70)
        print("Upload Complete!")
        print("=" * 70)
        print(f"  Locations:          {stats['locations']:>10,}")
        print(f"  Location Relations: {stats['location_relations']:>10,}")
        print(f"  Vehicles:           {stats['vehicles']:>10,}")
        print(f"  Routes:             {stats['routes']:>10,}")
        print(f"  Segments:           {stats['segments']:>10,}")
        print("=" * 70)
        print(f"  Total time:         {elapsed.total_seconds():.2f} seconds")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    main()
