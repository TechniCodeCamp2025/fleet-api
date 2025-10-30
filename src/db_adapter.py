"""
Database adapter for fleet optimization algorithms.
Handles all database I/O - algorithms don't touch CSV anymore.
"""
import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import os
import threading

from models import (
    Vehicle, Location, LocationRelation, Route, Segment,
    RouteAssignment, VehicleState, AssignmentConfig
)


# Global connection pool with thread safety
_connection_pool = None
_pool_lock = threading.Lock()


def get_connection_pool():
    """Get or create the global connection pool (thread-safe)"""
    global _connection_pool
    
    # Double-checked locking pattern for thread safety
    if _connection_pool is None:
        with _pool_lock:
            # Check again inside lock
            if _connection_pool is None:
                # Build connection string from environment variables
                conn_string = os.getenv('DATABASE_URL')
                
                if not conn_string:
                    # Build from individual env vars
                    db_host = os.getenv('DB_HOST', 'localhost')
                    db_port = os.getenv('DB_PORT', '5432')
                    db_name = os.getenv('DB_NAME', 'fleet_db')
                    db_user = os.getenv('DB_USER', 'postgres')
                    db_password = os.getenv('DB_PASSWORD', '')
                    
                    conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_password}"
                
                # Create connection pool
                min_conn = int(os.getenv('DB_POOL_MIN_CONN', '2'))
                max_conn = int(os.getenv('DB_POOL_MAX_CONN', '10'))
                
                _connection_pool = psycopg2.pool.SimpleConnectionPool(
                    min_conn,
                    max_conn,
                    conn_string
                )
                
                print(f"[✓] Database connection pool created ({min_conn}-{max_conn} connections)")
    
    return _connection_pool


class FleetDatabase:
    """Database adapter for algorithm I/O"""
    
    def __init__(self, conn_string: str = None, use_pool: bool = True):
        """
        Initialize database connection.
        
        Args:
            conn_string: Optional connection string (overrides env vars)
            use_pool: Use connection pool (recommended for production)
        """
        if use_pool and conn_string is None:
            # Get connection from pool
            pool = get_connection_pool()
            self.conn = pool.getconn()
            self._from_pool = True
        else:
            # Direct connection (for custom conn_string or testing)
            if conn_string is None:
                db_host = os.getenv('DB_HOST', 'localhost')
                db_port = os.getenv('DB_PORT', '5432')
                db_name = os.getenv('DB_NAME', 'fleet_db')
                db_user = os.getenv('DB_USER', 'postgres')
                db_password = os.getenv('DB_PASSWORD', '')
                
                conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_password}"
            
            self.conn = psycopg2.connect(conn_string)
            self._from_pool = False
        
        self.cur = self.conn.cursor(cursor_factory=RealDictCursor)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        
        # Close cursor to prevent resource leak
        if self.cur:
            self.cur.close()
        
        # Return connection to pool or close direct connection
        if self._from_pool:
            pool = get_connection_pool()
            pool.putconn(self.conn)
        else:
            self.conn.close()
    
    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            self.cur.execute("SELECT 1")
            result = self.cur.fetchone()
            return result is not None
        except Exception as e:
            print(f"[!] Database health check failed: {e}")
            return False
    
    def get_connection_info(self) -> Dict:
        """Get information about the database connection"""
        try:
            self.cur.execute("""
                SELECT 
                    current_database() as database,
                    current_user as user,
                    version() as version,
                    pg_size_pretty(pg_database_size(current_database())) as size
            """)
            info = dict(self.cur.fetchone())
            
            # Get table counts
            self.cur.execute("""
                SELECT 
                    (SELECT count(*) FROM locations) as locations,
                    (SELECT count(*) FROM location_relations) as location_relations,
                    (SELECT count(*) FROM vehicles) as vehicles,
                    (SELECT count(*) FROM routes) as routes,
                    (SELECT count(*) FROM segments) as segments,
                    (SELECT count(*) FROM assignments) as assignments
            """)
            counts = dict(self.cur.fetchone())
            info['table_counts'] = counts
            
            return info
        except Exception as e:
            return {"error": str(e)}
    
    # ========================================================================
    # READ Operations (for algorithms)
    # ========================================================================
    
    def load_locations(self) -> List[Location]:
        """Load all locations"""
        self.cur.execute("""
            SELECT id, name, lat, long, is_hub
            FROM locations
            ORDER BY id
        """)
        
        locations = []
        for row in self.cur.fetchall():
            locations.append(Location(
                id=row['id'],
                name=row['name'],
                lat=row['lat'],
                long=row['long'],
                is_hub=row['is_hub']
            ))
        
        print(f"[✓] Loaded {len(locations)} locations from DB")
        return locations
    
    def load_location_relations(self) -> Tuple[List[LocationRelation], Dict]:
        """Load location relations and create lookup dictionary"""
        self.cur.execute("""
            SELECT id, from_location_id, to_location_id, distance_km, time_minutes
            FROM location_relations
            ORDER BY id
        """)
        
        relations = []
        lookup = {}
        
        for row in self.cur.fetchall():
            relation = LocationRelation(
                id=row['id'],
                id_loc_1=row['from_location_id'],
                id_loc_2=row['to_location_id'],
                dist=row['distance_km'],
                time=row['time_minutes']  # Keep as minutes for algorithm compatibility
            )
            relations.append(relation)
            lookup[(relation.id_loc_1, relation.id_loc_2)] = relation
        
        print(f"[✓] Loaded {len(relations)} location relations from DB")
        return relations, lookup
    
    def load_vehicles(self) -> List[Vehicle]:
        """Load all vehicles"""
        self.cur.execute("""
            SELECT id, registration_number, brand, service_interval_km,
                   leasing_start_km, leasing_limit_km, leasing_start_date,
                   leasing_end_date, current_odometer_km, current_location_id
            FROM vehicles
            ORDER BY id
        """)
        
        vehicles = []
        for row in self.cur.fetchall():
            vehicles.append(Vehicle(
                id=row['id'],
                registration_number=row['registration_number'],
                brand=row['brand'],
                service_interval_km=row['service_interval_km'],
                leasing_start_km=row['leasing_start_km'],
                leasing_limit_km=row['leasing_limit_km'],
                leasing_start_date=row['leasing_start_date'],
                leasing_end_date=row['leasing_end_date'],
                current_odometer_km=row['current_odometer_km'],
                current_location_id=row['current_location_id']
            ))
        
        print(f"[✓] Loaded {len(vehicles)} vehicles from DB")
        return vehicles
    
    def load_routes(self, status: str = 'pending') -> List[Route]:
        """Load routes with segments"""
        # Load routes
        self.cur.execute("""
            SELECT id, start_datetime, end_datetime, distance_km
            FROM routes
            WHERE status = %s
            ORDER BY start_datetime, id
        """, (status,))
        
        routes_data = self.cur.fetchall()
        
        # Load all segments for these routes
        if routes_data:
            route_ids = [r['id'] for r in routes_data]
            self.cur.execute("""
                SELECT id, route_id, seq, start_location_id, end_location_id,
                       start_datetime, end_datetime, distance_km, relation_id
                FROM segments
                WHERE route_id = ANY(%s)
                ORDER BY route_id, seq
            """, (route_ids,))
            
            segments_data = self.cur.fetchall()
            
            # Group segments by route_id
            segments_by_route = {}
            for seg in segments_data:
                route_id = seg['route_id']
                if route_id not in segments_by_route:
                    segments_by_route[route_id] = []
                
                segments_by_route[route_id].append(Segment(
                    id=seg['id'],
                    route_id=seg['route_id'],
                    seq=seg['seq'],
                    start_loc_id=seg['start_location_id'],
                    end_loc_id=seg['end_location_id'],
                    start_datetime=seg['start_datetime'],
                    end_datetime=seg['end_datetime'],
                    distance_travelled_km=seg['distance_km'],
                    relation_id=seg['relation_id']
                ))
        else:
            segments_by_route = {}
        
        # Create Route objects
        routes = []
        for row in routes_data:
            routes.append(Route(
                id=row['id'],
                start_datetime=row['start_datetime'],
                end_datetime=row['end_datetime'],
                distance_km=row['distance_km'],
                segments=segments_by_route.get(row['id'], [])
            ))
        
        print(f"[✓] Loaded {len(routes)} routes (status={status}) from DB")
        return routes
    
    def load_all_data(self) -> Tuple[List[Vehicle], List[Location], Dict, List[Route]]:
        """Load all data for algorithms"""
        print(f"\n[*] Loading data from database...")
        
        vehicles = self.load_vehicles()
        locations = self.load_locations()
        relations, relation_lookup = self.load_location_relations()
        routes = self.load_routes(status='pending')
        
        print(f"[✓] All data loaded from DB\n")
        
        return vehicles, locations, relation_lookup, routes
    
    # ========================================================================
    # WRITE Operations (for algorithm results)
    # ========================================================================
    
    def start_algorithm_run(self, config: dict = None) -> int:
        """Start a new algorithm run, returns run_id"""
        self.cur.execute("""
            INSERT INTO algorithm_runs (config, status)
            VALUES (%s, 'running')
            RETURNING id
        """, (psycopg2.extras.Json(config) if config else None,))
        
        run_id = self.cur.fetchone()['id']
        self.conn.commit()
        
        print(f"[*] Started algorithm run {run_id}")
        return run_id
    
    def complete_algorithm_run(
        self,
        run_id: int,
        routes_processed: int = None,
        assignments_created: int = None,
        total_cost: float = None,
        error: str = None
    ):
        """Mark algorithm run as complete"""
        status = 'failed' if error else 'completed'
        
        self.cur.execute("""
            UPDATE algorithm_runs
            SET completed_at = current_timestamp,
                status = %s,
                routes_processed = %s,
                assignments_created = %s,
                total_cost_pln = %s,
                error_message = %s
            WHERE id = %s
        """, (status, routes_processed, assignments_created, total_cost, error, run_id))
        
        self.conn.commit()
        print(f"[✓] Completed algorithm run {run_id} (status={status})")
    
    def save_assignment(
        self,
        assignment: RouteAssignment,
        run_id: int
    ) -> int:
        """Save a single assignment and its costs"""
        # Create assignment
        self.cur.execute("""
            INSERT INTO assignments (route_id, vehicle_id, algorithm_run_id)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (assignment.route_id, assignment.vehicle_id, run_id))
        
        assignment_id = self.cur.fetchone()['id']
        
        # Save costs
        self.cur.execute("""
            INSERT INTO assignment_costs (
                assignment_id, relocation_cost_pln, overage_cost_pln,
                service_cost_pln, requires_relocation, requires_service,
                overage_km, chain_score
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            assignment_id,
            assignment.assignment_cost if assignment.requires_relocation else 0,
            0,  # overage calculated separately
            0,  # service cost
            assignment.requires_relocation,
            assignment.requires_service,
            assignment.overage_km,
            assignment.chain_score
        ))
        
        # Save relocation if needed
        if assignment.requires_relocation and assignment.relocation_from:
            self.cur.execute("""
                INSERT INTO relocations (
                    assignment_id, vehicle_id, from_location_id, to_location_id,
                    distance_km, time_hours, cost_pln, scheduled_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                assignment_id,
                assignment.vehicle_id,
                assignment.relocation_from,
                assignment.relocation_to,
                assignment.relocation_distance,
                assignment.relocation_time,
                assignment.assignment_cost,
                assignment.date
            ))
        
        return assignment_id
    
    def save_vehicle_state(
        self,
        vehicle_state: VehicleState,
        run_id: int,
        assignment_id: int = None
    ):
        """Save vehicle state snapshot"""
        self.cur.execute("""
            INSERT INTO vehicle_states (
                vehicle_id, assignment_id, algorithm_run_id, location_id,
                odometer_km, km_since_service, km_this_lease_year, event_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'assignment')
        """, (
            vehicle_state.vehicle_id,
            assignment_id,
            run_id,
            vehicle_state.current_location_id,
            vehicle_state.current_odometer_km,
            vehicle_state.km_since_last_service,
            vehicle_state.km_driven_this_lease_year
        ))
    
    def save_all_results(
        self,
        assignments: List[RouteAssignment],
        vehicle_states: Dict[int, VehicleState],
        run_id: int
    ):
        """Bulk save all algorithm results with transaction safety"""
        print(f"\n[*] Saving {len(assignments)} assignments to database...")
        
        try:
            # Start transaction
            for assignment in assignments:
                assignment_id = self.save_assignment(assignment, run_id)
                
                # Save vehicle state if available
                if assignment.vehicle_id in vehicle_states:
                    self.save_vehicle_state(
                        vehicle_states[assignment.vehicle_id],
                        run_id,
                        assignment_id
                    )
            
            # Commit all changes atomically
            self.conn.commit()
            print(f"[✓] Saved all results to database")
        except Exception as e:
            # Rollback on any error to maintain consistency
            self.conn.rollback()
            print(f"[✗] Error saving results: {e}")
            raise
    
    # ========================================================================
    # CSV IMPORT (upsert - no conflicts)
    # ========================================================================
    
    def import_location(self, row: dict) -> int:
        """Import single location"""
        self.cur.execute("""
            SELECT upsert_location(%s, %s, %s, %s, %s)
        """, (
            int(row['id']),
            row['name'],
            float(row['lat']),
            float(row['long']),
            bool(int(row['is_hub']))
        ))
        return self.cur.fetchone()['upsert_location']
    
    def import_location_relation(self, row: dict) -> int:
        """Import single location relation"""
        self.cur.execute("""
            SELECT upsert_location_relation(%s, %s, %s, %s, %s)
        """, (
            int(row['id']),
            int(row['id_loc_1']),
            int(row['id_loc_2']),
            float(row['dist']),
            float(row['time'])
        ))
        return self.cur.fetchone()['upsert_location_relation']
    
    def import_vehicle(self, row: dict) -> int:
        """Import single vehicle"""
        loc_id = None
        if row.get('Current_location_id') and row['Current_location_id'] not in ('N/A', '', 'None'):
            loc_id = int(row['Current_location_id'])
        
        self.cur.execute("""
            SELECT upsert_vehicle(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            int(row['Id']),
            row['registration_number'],
            row['brand'],
            int(row['service_interval_km']),
            int(row['Leasing_start_km']),
            int(row['leasing_limit_km']),
            row['leasing_start_date'],
            row['leasing_end_date'],
            int(row['current_odometer_km']),
            loc_id
        ))
        return self.cur.fetchone()['upsert_vehicle']
    
    def import_route(self, row: dict) -> int:
        """Import single route"""
        self.cur.execute("""
            SELECT upsert_route(%s, %s, %s, %s)
        """, (
            int(row['id']),
            row['start_datetime'],
            row['end_datetime'],
            float(row['distance_km'])
        ))
        return self.cur.fetchone()['upsert_route']
    
    def import_segment(self, row: dict) -> int:
        """Import single segment"""
        self.cur.execute("""
            SELECT upsert_segment(%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            int(row['id']),
            int(row['route_id']),
            int(row['seq']),
            int(row['start_loc_id']),
            int(row['end_loc_id']),
            row['start_datetime'],
            row['end_datetime'],
            float(row.get('distance_km', 0)),
            int(row['relation_id'])
        ))
        return self.cur.fetchone()['upsert_segment']

