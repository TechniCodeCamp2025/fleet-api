"""
Data loading utilities for CSV files.
"""
import csv
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
from pathlib import Path

from models import Vehicle, Location, LocationRelation, Route, Segment


def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string from CSV"""
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Try alternative formats
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return datetime.strptime(dt_str, "%Y-%m-%d")


def parse_optional_int(value: str) -> int | None:
    """Parse integer or return None for N/A"""
    if value == "N/A" or value == "" or value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def load_vehicles(csv_path: str) -> List[Vehicle]:
    """Load vehicles from CSV"""
    vehicles = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vehicle = Vehicle(
                id=int(row['Id']),
                registration_number=row['registration_number'],
                brand=row['brand'],
                service_interval_km=int(row['service_interval_km']),
                leasing_start_km=int(row['Leasing_start_km']),
                leasing_limit_km=int(row['leasing_limit_km']),
                leasing_start_date=parse_datetime(row['leasing_start_date']),
                leasing_end_date=parse_datetime(row['leasing_end_date']),
                current_odometer_km=int(row['current_odometer_km']),
                current_location_id=parse_optional_int(row['Current_location_id'])
            )
            vehicles.append(vehicle)
    
    print(f"[✓] Loaded {len(vehicles)} vehicles")
    return vehicles


def load_locations(csv_path: str) -> List[Location]:
    """Load locations from CSV"""
    locations = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            location = Location(
                id=int(row['id']),
                name=row['name'],
                lat=float(row['lat']),
                long=float(row['long']),
                is_hub=bool(int(row['is_hub']))
            )
            locations.append(location)
    
    print(f"[✓] Loaded {len(locations)} locations")
    return locations


def load_location_relations(csv_path: str) -> Tuple[List[LocationRelation], Dict]:
    """Load location relations and create lookup dictionary"""
    relations = []
    lookup = {}  # (loc1, loc2) -> LocationRelation
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            relation = LocationRelation(
                id=int(row['id']),
                id_loc_1=int(row['id_loc_1']),
                id_loc_2=int(row['id_loc_2']),
                dist=float(row['dist']),
                time=float(row['time'])
            )
            relations.append(relation)
            lookup[(relation.id_loc_1, relation.id_loc_2)] = relation
    
    print(f"[✓] Loaded {len(relations)} location relations")
    return relations, lookup


def load_segments(csv_path: str) -> Dict[int, List[Segment]]:
    """Load segments grouped by route_id"""
    segments_by_route = defaultdict(list)
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            segment = Segment(
                id=int(row['id']),
                route_id=int(row['route_id']),
                seq=int(row['seq']),
                start_loc_id=int(row['start_loc_id']),
                end_loc_id=int(row['end_loc_id']),
                start_datetime=parse_datetime(row['start_datetime']),
                end_datetime=parse_datetime(row['end_datetime']),
                distance_travelled_km=float(row['relation_id']),  # This seems to be distance based on the data
                relation_id=int(row['relation_id'])
            )
            segments_by_route[segment.route_id].append(segment)
    
    # Sort segments by sequence
    for route_id in segments_by_route:
        segments_by_route[route_id].sort(key=lambda s: s.seq)
    
    total_segments = sum(len(segs) for segs in segments_by_route.values())
    print(f"[✓] Loaded {total_segments} segments for {len(segments_by_route)} routes")
    return dict(segments_by_route)


def load_routes(csv_path: str, segments_by_route: Dict[int, List[Segment]]) -> List[Route]:
    """Load routes from CSV and attach segments"""
    routes = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            route_id = int(row['id'])
            route = Route(
                id=route_id,
                start_datetime=parse_datetime(row['start_datetime']),
                end_datetime=parse_datetime(row['end_datetime']),
                distance_km=float(row['distance_km']),
                segments=segments_by_route.get(route_id, [])
            )
            routes.append(route)
    
    # Sort routes by start datetime
    routes.sort(key=lambda r: r.start_datetime)
    
    print(f"[✓] Loaded {len(routes)} routes")
    return routes


def load_all_data(data_dir: str) -> Tuple[List[Vehicle], List[Location], Dict, List[Route]]:
    """Load all data from CSV files"""
    data_path = Path(data_dir)
    
    print(f"\n[*] Loading data from {data_dir}...")
    
    # Load all data
    vehicles = load_vehicles(str(data_path / "vehicles.csv"))
    locations = load_locations(str(data_path / "locations.csv"))
    relations, relation_lookup = load_location_relations(str(data_path / "locations_relations.csv"))
    segments_by_route = load_segments(str(data_path / "segments.csv"))
    routes = load_routes(str(data_path / "routes.csv"), segments_by_route)
    
    print(f"[✓] All data loaded successfully\n")
    
    return vehicles, locations, relation_lookup, routes


def get_relation(from_loc: int, to_loc: int, relation_lookup: Dict, use_pathfinding: bool = True) -> LocationRelation | None:
    """
    Get relation between two locations.
    If no direct relation exists, tries to find multi-hop path.
    """
    # Same location
    if from_loc == to_loc:
        return LocationRelation(id=0, id_loc_1=from_loc, id_loc_2=to_loc, dist=0.0, time=0.0)
    
    # Try direct
    if (from_loc, to_loc) in relation_lookup:
        return relation_lookup[(from_loc, to_loc)]
    
    # Try reverse (assuming bidirectional)
    if (to_loc, from_loc) in relation_lookup:
        return relation_lookup[(to_loc, from_loc)]
    
    # If no direct path and pathfinding enabled, find multi-hop route
    if use_pathfinding:
        from pathfinding import get_path_with_cache
        path_result = get_path_with_cache(from_loc, to_loc, relation_lookup)
        
        if path_result.exists:
            # Create synthetic relation for the multi-hop path
            return LocationRelation(
                id=-1,  # Synthetic
                id_loc_1=from_loc,
                id_loc_2=to_loc,
                dist=path_result.distance_km,
                time=path_result.time_hours
            )
    
    return None

