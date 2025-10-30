"""
Vehicle placement algorithm - determines initial location for each vehicle.
Cost-based proportional distribution strategy.
"""
from collections import defaultdict, Counter
from datetime import timedelta
from typing import List, Dict, Tuple
from models import Vehicle, Route, Location, PlacementResult, AssignmentConfig
from costs import calculate_placement_cost


def analyze_demand(
    routes: List[Route],
    lookahead_days: int = 14
) -> Dict[int, int]:
    """
    Analyze demand for each location based on route start locations.
    
    Args:
        routes: All routes (should be sorted by date)
        lookahead_days: Number of days to analyze
    
    Returns:
        Dictionary mapping location_id to route count
    """
    demand = defaultdict(int)
    
    if not routes:
        return demand
    
    # Get time window
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    
    # Count routes per location
    for route in routes:
        if route.start_datetime >= end_date:
            break  # Routes are sorted, so we can stop
        
        if route.start_location_id:
            demand[route.start_location_id] += 1
    
    return dict(demand)


def sort_locations_by_demand(demand: Dict[int, int]) -> List[Tuple[int, int]]:
    """
    Sort locations by demand (highest first).
    
    Returns:
        List of (location_id, route_count) tuples
    """
    return sorted(demand.items(), key=lambda x: x[1], reverse=True)


def distribute_vehicles_proportionally(
    sorted_locations: List[Tuple[int, int]],
    vehicles: List[Vehicle],
    max_concentration: float = 0.30
) -> Dict[int, int]:
    """
    Distribute vehicles proportionally to demand.
    
    Args:
        sorted_locations: Locations sorted by demand
        vehicles: List of all vehicles
        max_concentration: Maximum fraction of fleet at one location
    
    Returns:
        Dictionary mapping vehicle_id to location_id
    """
    if not sorted_locations:
        # Fallback: place all at first vehicle's location or location 1
        if not vehicles:
            return {}
        fallback_loc = vehicles[0].current_location_id if vehicles[0].current_location_id else 1
        return {v.id: fallback_loc for v in vehicles}
    
    placement = {}
    total_demand = sum(count for _, count in sorted_locations)
    vehicle_index = 0
    max_per_location = max(1, int(len(vehicles) * max_concentration))
    
    for loc_id, demand_count in sorted_locations:
        if vehicle_index >= len(vehicles):
            break
        
        # Calculate proportion (safe division)
        proportion = demand_count / total_demand if total_demand > 0 else 1.0 / len(sorted_locations)
        vehicles_needed = max(1, int(len(vehicles) * proportion))
        
        # Apply concentration limit
        vehicles_needed = min(vehicles_needed, max_per_location)
        
        # Don't over-allocate
        vehicles_needed = min(vehicles_needed, len(vehicles) - vehicle_index)
        
        # Assign vehicles to this location
        for _ in range(vehicles_needed):
            if vehicle_index >= len(vehicles):
                break
            placement[vehicles[vehicle_index].id] = loc_id
            vehicle_index += 1
    
    # Assign any remaining vehicles to top location
    if vehicle_index < len(vehicles):
        top_location = sorted_locations[0][0]
        for i in range(vehicle_index, len(vehicles)):
            placement[vehicles[i].id] = top_location
    
    return placement


def calculate_placement_statistics(
    placement: Dict[int, int],
    demand: Dict[int, int]
) -> Dict:
    """Calculate statistics about the placement"""
    location_counts = Counter(placement.values())
    
    stats = {
        'total_vehicles': len(placement),
        'locations_used': len(location_counts),
        'avg_vehicles_per_location': len(placement) / len(location_counts) if location_counts else 0,
        'max_vehicles_at_location': max(location_counts.values()) if location_counts else 0,
        'min_vehicles_at_location': min(location_counts.values()) if location_counts else 0,
        'top_location_id': location_counts.most_common(1)[0][0] if location_counts else None,
        'top_location_count': location_counts.most_common(1)[0][1] if location_counts else 0,
        'concentration_ratio': location_counts.most_common(1)[0][1] / len(placement) if location_counts and placement else 0,
    }
    
    # Check if vehicles at zero-demand locations
    zero_demand_locations = set()
    for v_id, loc_id in placement.items():
        if demand.get(loc_id, 0) == 0:
            zero_demand_locations.add(loc_id)
    
    stats['vehicles_at_zero_demand'] = sum(1 for loc in zero_demand_locations for v in placement.values() if v == loc)
    
    return stats


def calculate_placement(
    vehicles: List[Vehicle],
    routes: List[Route],
    locations: List[Location],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> PlacementResult:
    """
    Main placement algorithm - proportional distribution based on demand.
    
    Args:
        vehicles: All vehicles to place
        routes: All routes (sorted by date)
        locations: All locations
        relation_lookup: Location relations lookup
        config: Configuration
    
    Returns:
        PlacementResult with placement and statistics
    """
    print("\n" + "="*60)
    print("PLACEMENT ALGORITHM - Cost-Based Proportional Distribution")
    print("="*60)
    
    # Step 1: Analyze demand
    print(f"\n[*] Step 1: Analyzing demand (first {config.placement_lookahead_days} days)...")
    demand = analyze_demand(routes, config.placement_lookahead_days)
    print(f"    Found demand at {len(demand)} locations")
    
    # Step 2: Sort locations by demand
    print(f"\n[*] Step 2: Sorting locations by demand...")
    sorted_locations = sort_locations_by_demand(demand)
    
    if sorted_locations:
        top_5 = sorted_locations[:5]
        print(f"    Top 5 locations:")
        for loc_id, count in top_5:
            print(f"      Location {loc_id}: {count} routes")
    
    # Step 3: Distribute vehicles proportionally
    print(f"\n[*] Step 3: Distributing {len(vehicles)} vehicles proportionally...")
    placement = distribute_vehicles_proportionally(sorted_locations, vehicles)
    
    # Calculate statistics
    stats = calculate_placement_statistics(placement, demand)
    
    print(f"\n[*] Placement Statistics:")
    print(f"    Total vehicles placed: {stats['total_vehicles']}")
    print(f"    Locations used: {stats['locations_used']}")
    print(f"    Avg vehicles per location: {stats['avg_vehicles_per_location']:.1f}")
    print(f"    Max at one location: {stats['max_vehicles_at_location']} (location {stats['top_location_id']})")
    print(f"    Concentration ratio: {stats['concentration_ratio']:.1%}")
    print(f"    Vehicles at zero-demand locations: {stats['vehicles_at_zero_demand']}")
    
    # Estimate placement quality
    print(f"\n[*] Estimating placement quality...")
    estimated_cost = calculate_placement_cost(
        placement,
        routes,
        relation_lookup,
        config,
        config.placement_lookahead_days
    )
    print(f"    Estimated early relocation cost: {estimated_cost:,.2f} PLN")
    
    # Validate placement quality
    if stats['concentration_ratio'] > 0.5:
        print(f"    ⚠️  WARNING: High concentration ({stats['concentration_ratio']:.1%}) at one location")
    elif stats['concentration_ratio'] < 0.05:
        print(f"    ⚠️  WARNING: Too scattered (top location only {stats['concentration_ratio']:.1%})")
    else:
        print(f"    ✅ Good clustering")
    
    if stats['vehicles_at_zero_demand'] > 0:
        print(f"    ⚠️  WARNING: {stats['vehicles_at_zero_demand']} vehicles at zero-demand locations")
    else:
        print(f"    ✅ All vehicles at demand locations")
    
    if estimated_cost > 10_000_000:
        print(f"    ⚠️  WARNING: High estimated cost (>{estimated_cost:,.0f} PLN)")
    else:
        print(f"    ✅ Reasonable estimated cost")
    
    print("\n" + "="*60)
    print("PLACEMENT COMPLETE")
    print("="*60 + "\n")
    
    return PlacementResult(
        placements=placement,
        demand_analysis=demand,
        total_vehicles_placed=stats['total_vehicles'],
        locations_used=stats['locations_used'],
        avg_vehicles_per_location=stats['avg_vehicles_per_location']
    )


def apply_placement_to_vehicles(
    vehicles: List[Vehicle],
    placement: Dict[int, int]
) -> None:
    """
    Apply placement result to vehicle objects (mutate in place).
    """
    for vehicle in vehicles:
        if vehicle.id in placement:
            vehicle.current_location_id = placement[vehicle.id]

