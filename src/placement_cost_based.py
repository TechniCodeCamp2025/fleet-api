"""
Cost-based vehicle placement algorithm.
Minimizes initial relocation costs by optimally placing vehicles.
"""
from collections import defaultdict
from datetime import timedelta
from typing import List, Dict, Tuple
from models import Vehicle, Route, Location, PlacementResult, AssignmentConfig
from costs import calculate_relocation_cost
from data_loader import get_relation


def analyze_initial_demand(
    routes: List[Route],
    lookahead_days: int = 14
) -> Dict[int, List[Route]]:
    """
    Group routes by starting location for the initial period.
    
    Returns:
        Dict mapping location_id to list of routes starting there
    """
    demand_by_location = defaultdict(list)
    
    if not routes:
        return demand_by_location
    
    # Get time window
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    
    # Group routes by start location
    for route in routes:
        if route.start_datetime >= end_date:
            break  # Routes are sorted
        
        if route.start_location_id:
            demand_by_location[route.start_location_id].append(route)
    
    return dict(demand_by_location)


def calculate_placement_cost_for_location(
    location_id: int,
    vehicle_count: int,
    routes_at_location: List[Route],
    all_demand: Dict[int, List[Route]],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> float:
    """
    Calculate expected cost if we place {vehicle_count} vehicles at {location_id}.
    
    Logic:
    - Vehicles at this location can serve local routes for free
    - But may need to relocate to serve routes at other locations
    - Calculate expected relocation cost based on demand distribution
    """
    if vehicle_count == 0:
        return 0.0
    
    total_cost = 0.0
    
    # Cost to serve routes at OTHER locations (relocations needed)
    for other_loc_id, other_routes in all_demand.items():
        if other_loc_id == location_id:
            continue  # No cost for local routes
        
        # Calculate relocation cost to this other location
        reloc_cost, _, _ = calculate_relocation_cost(
            location_id, other_loc_id, relation_lookup, config
        )
        
        if reloc_cost < 999999:  # Path exists
            # Estimate: assume proportional sharing of routes
            # This is a heuristic - we don't know exact assignments yet
            expected_routes_to_serve = len(other_routes) * (vehicle_count / 100)  # Rough estimate
            total_cost += expected_routes_to_serve * reloc_cost * 0.1  # Weighted by probability
    
    return total_cost


def cost_based_greedy_placement(
    vehicles: List[Vehicle],
    demand_by_location: Dict[int, List[Route]],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Dict[int, int]:
    """
    Greedy cost-based placement:
    For each vehicle, place it at the location that minimizes expected total cost.
    """
    placement = {}
    
    # Sort locations by demand (start with highest demand)
    sorted_locations = sorted(
        demand_by_location.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    if not sorted_locations:
        # Fallback: place all at location 1
        return {v.id: 1 for v in vehicles}
    
    # Count vehicles already placed at each location
    vehicles_at_location = defaultdict(int)
    
    # Greedy assignment: place each vehicle at location with highest demand
    for vehicle in vehicles:
        best_location = None
        best_score = float('-inf')
        
        # Evaluate each location
        for loc_id, routes in sorted_locations:
            # Score = demand at location - cost penalty for being far from other demands
            local_demand = len(routes)
            
            # Prefer locations with high demand and few vehicles already
            current_count = vehicles_at_location[loc_id]
            
            # Score higher if more demand and fewer vehicles
            score = local_demand / (current_count + 1)
            
            if score > best_score:
                best_score = score
                best_location = loc_id
        
        if best_location:
            placement[vehicle.id] = best_location
            vehicles_at_location[best_location] += 1
        else:
            # Fallback to first location
            placement[vehicle.id] = sorted_locations[0][0]
            vehicles_at_location[sorted_locations[0][0]] += 1
    
    return placement


def cost_based_clustering_placement(
    vehicles: List[Vehicle],
    demand_by_location: Dict[int, List[Route]],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Dict[int, int]:
    """
    Cost-based clustering placement:
    Place vehicles to minimize expected relocation costs.
    
    Strategy:
    1. Identify high-demand clusters
    2. Allocate vehicles proportionally, but with cost penalties for poor locations
    3. Ensure no over-concentration
    """
    placement = {}
    
    if not demand_by_location:
        return {v.id: 1 for v in vehicles}
    
    # Calculate "attractiveness" of each location (demand / cost to reach other demands)
    location_scores = {}
    total_routes = sum(len(routes) for routes in demand_by_location.values())
    
    for loc_id, routes in demand_by_location.items():
        local_demand = len(routes)
        
        # Calculate average relocation cost to other high-demand locations
        avg_reloc_cost = 0.0
        cost_count = 0
        
        for other_loc_id, other_routes in demand_by_location.items():
            if other_loc_id == loc_id:
                continue
            
            if len(other_routes) < 10:  # Only consider significant demand
                continue
            
            reloc_cost, _, _ = calculate_relocation_cost(
                loc_id, other_loc_id, relation_lookup, config
            )
            
            if reloc_cost < 999999:
                # Weight by demand at destination
                weight = len(other_routes) / total_routes
                avg_reloc_cost += reloc_cost * weight
                cost_count += weight
        
        if cost_count > 0:
            avg_reloc_cost /= cost_count
        else:
            avg_reloc_cost = 10000  # Penalty for isolated locations
        
        # Score = demand / (1 + avg_cost/1000)
        # Higher demand and lower avg cost = higher score
        score = local_demand / (1 + avg_reloc_cost / 1000)
        location_scores[loc_id] = (score, local_demand)
    
    # Sort locations by score
    sorted_locs = sorted(
        location_scores.items(),
        key=lambda x: x[1][0],  # Sort by score
        reverse=True
    )
    
    # Allocate vehicles proportionally to scores, with limits
    total_score = sum(score for _, (score, _) in sorted_locs)
    vehicles_allocated = 0
    max_per_location = max(5, int(len(vehicles) * 0.3))  # At least 5, max 30%
    
    for loc_id, (score, demand) in sorted_locs:
        if vehicles_allocated >= len(vehicles):
            break
        
        # Allocate proportional to score
        proportion = score / total_score if total_score > 0 else 1 / len(sorted_locs)
        vehicles_needed = int(len(vehicles) * proportion)
        
        # Apply limits
        vehicles_needed = max(1, min(vehicles_needed, max_per_location))
        vehicles_needed = min(vehicles_needed, len(vehicles) - vehicles_allocated)
        
        # Assign vehicles
        for i in range(vehicles_allocated, vehicles_allocated + vehicles_needed):
            if i < len(vehicles):
                placement[vehicles[i].id] = loc_id
        
        vehicles_allocated += vehicles_needed
    
    # Assign remaining vehicles to top location
    if vehicles_allocated < len(vehicles):
        top_location = sorted_locs[0][0]
        for i in range(vehicles_allocated, len(vehicles)):
            placement[vehicles[i].id] = top_location
    
    return placement


def calculate_cost_based_placement(
    vehicles: List[Vehicle],
    routes: List[Route],
    locations: List[Location],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> PlacementResult:
    """
    Main cost-based placement algorithm.
    """
    print("\n" + "="*60)
    print("COST-BASED PLACEMENT ALGORITHM")
    print("="*60)
    
    # Step 1: Analyze demand
    print(f"\n[*] Step 1: Analyzing demand (first {config.placement_lookahead_days} days)...")
    demand_by_location = analyze_initial_demand(routes, config.placement_lookahead_days)
    total_routes = sum(len(r) for r in demand_by_location.values())
    print(f"    Found {total_routes} routes across {len(demand_by_location)} locations")
    
    # Step 2: Calculate cost-based placement
    print(f"\n[*] Step 2: Calculating cost-optimized placement...")
    placement = cost_based_clustering_placement(
        vehicles, demand_by_location, relation_lookup, config
    )
    
    # Step 3: Calculate statistics
    from collections import Counter
    location_counts = Counter(placement.values())
    
    stats = {
        'total_vehicles': len(placement),
        'locations_used': len(location_counts),
        'max_at_location': max(location_counts.values()) if location_counts else 0,
        'concentration': max(location_counts.values()) / len(vehicles) if vehicles else 0
    }
    
    print(f"\n[*] Placement Statistics:")
    print(f"    Vehicles placed: {stats['total_vehicles']}")
    print(f"    Locations used: {stats['locations_used']}")
    print(f"    Max at one location: {stats['max_at_location']}")
    print(f"    Concentration: {stats['concentration']:.1%}")
    
    # Show distribution
    print(f"\n[*] Top 10 locations by vehicle count:")
    for i, (loc_id, count) in enumerate(location_counts.most_common(10)):
        demand = len(demand_by_location.get(loc_id, []))
        print(f"    {i+1}. Location {loc_id}: {count} vehicles, {demand} routes")
    
    # Estimate quality
    print(f"\n[*] Estimating placement quality...")
    
    # Calculate expected relocation cost
    expected_cost = 0.0
    relocations_needed = 0
    
    for loc_id, routes_list in demand_by_location.items():
        vehicles_here = location_counts.get(loc_id, 0)
        routes_here = len(routes_list)
        
        if routes_here > vehicles_here:
            # Will need relocations to serve excess demand
            deficit = routes_here - vehicles_here
            relocations_needed += deficit
            # Rough estimate: assume avg cost of 2000 PLN per relocation
            expected_cost += deficit * 2000
    
    print(f"    Expected relocations needed: {relocations_needed}")
    print(f"    Estimated cost: {expected_cost:,.0f} PLN")
    
    if expected_cost < 5_000_000:
        print(f"    ✅ Excellent placement (cost < 5M PLN)")
    elif expected_cost < 20_000_000:
        print(f"    ✅ Good placement (cost < 20M PLN)")
    else:
        print(f"    ⚠️  High expected cost")
    
    print("\n" + "="*60)
    print("COST-BASED PLACEMENT COMPLETE")
    print("="*60 + "\n")
    
    # Create result
    demand_counts = {loc_id: len(routes_list) for loc_id, routes_list in demand_by_location.items()}
    
    return PlacementResult(
        placements=placement,
        demand_analysis=demand_counts,
        total_vehicles_placed=len(placement),
        locations_used=len(location_counts),
        avg_vehicles_per_location=len(placement) / len(location_counts) if location_counts else 0
    )

