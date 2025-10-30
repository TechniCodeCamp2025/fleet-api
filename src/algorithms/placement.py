"""
Core placement algorithm - pure logic, no I/O.
Determines optimal initial vehicle placement to minimize relocation costs.
"""
from typing import List, Dict, Tuple
from datetime import timedelta
from collections import defaultdict
import numpy as np


def analyze_demand(routes: List, lookahead_days: int = 14) -> Dict[int, int]:
    """
    Count routes starting at each location in the initial period.
    
    Returns:
        {location_id: route_count}
    """
    demand = defaultdict(int)
    
    if not routes:
        return dict(demand)
    
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    
    for route in routes:
        if route.start_datetime >= end_date:
            break
        if route.start_location_id:
            demand[route.start_location_id] += 1
    
    return dict(demand)


def build_cost_matrix(
    vehicles: List,
    demand: Dict[int, int],
    relation_lookup: Dict,
    config
) -> Tuple[np.ndarray, List[int], List[int]]:
    """
    Build cost matrix for vehicle-location assignments.
    
    Cost[i, j] = cost of placing vehicle i at location j
    
    Cost calculation:
    - If location has high demand: lower cost (good match)
    - If location is well-connected: lower cost (can reach other locations)
    - If location has no demand: high penalty
    
    Returns:
        (cost_matrix, vehicle_ids, location_ids)
    """
    if not demand:
        # No demand data - uniform cost
        locations = [1]  # Fallback location
        n_vehicles = len(vehicles)
        n_locations = 1
        cost_matrix = np.ones((n_vehicles, n_locations)) * 1000
        return cost_matrix, [v.id for v in vehicles], locations
    
    # Get candidate locations (those with demand)
    locations = sorted(demand.keys())
    n_vehicles = len(vehicles)
    n_locations = len(locations)
    
    # Initialize cost matrix
    cost_matrix = np.zeros((n_vehicles, n_locations))
    
    # Calculate cost for each vehicle-location pair
    for i, vehicle in enumerate(vehicles):
        for j, loc_id in enumerate(locations):
            # Base cost inversely proportional to demand
            # High demand = low cost (good to place vehicles there)
            local_demand = demand[loc_id]
            base_cost = 10000 / (local_demand + 1)
            
            # Calculate connectivity cost
            # Well-connected locations are cheaper
            connectivity_penalty = 0
            other_locations = [l for l in locations if l != loc_id]
            
            if other_locations:
                connected_count = 0
                for other_loc in other_locations[:10]:  # Check top 10 other locations
                    # Check if path exists
                    if (loc_id, other_loc) in relation_lookup or (other_loc, loc_id) in relation_lookup:
                        connected_count += 1
                
                # Penalty if poorly connected
                if connected_count < len(other_locations[:10]) * 0.3:
                    connectivity_penalty = 5000
            
            # Total cost
            cost_matrix[i, j] = base_cost + connectivity_penalty
    
    return cost_matrix, [v.id for v in vehicles], locations


def greedy_min_cost_assignment(
    cost_matrix: np.ndarray,
    vehicle_ids: List[int],
    location_ids: List[int],
    max_per_location: int = None
) -> Dict[int, int]:
    """
    Greedy assignment minimizing total cost.
    
    Strategy:
    - Iteratively assign each vehicle to the cheapest available location
    - Respect capacity constraints (max vehicles per location)
    
    Returns:
        {vehicle_id: location_id}
    """
    n_vehicles, n_locations = cost_matrix.shape
    
    if n_locations == 0:
        return {vid: 1 for vid in vehicle_ids}  # Fallback
    
    # Default: max 30% of fleet at one location
    if max_per_location is None:
        max_per_location = max(5, int(n_vehicles * 0.30))
    
    placement = {}
    location_counts = defaultdict(int)
    
    # Sort vehicles by their minimum cost (assign hardest first)
    vehicle_order = []
    for i in range(n_vehicles):
        min_cost = cost_matrix[i, :].min()
        vehicle_order.append((min_cost, i, vehicle_ids[i]))
    
    vehicle_order.sort(reverse=True)  # Hardest first
    
    for _, v_idx, v_id in vehicle_order:
        # Find cheapest available location
        best_loc_idx = None
        best_cost = float('inf')
        
        for l_idx in range(n_locations):
            loc_id = location_ids[l_idx]
            
            # Check capacity
            if location_counts[loc_id] >= max_per_location:
                continue
            
            cost = cost_matrix[v_idx, l_idx]
            if cost < best_cost:
                best_cost = cost
                best_loc_idx = l_idx
        
        # Assign
        if best_loc_idx is not None:
            loc_id = location_ids[best_loc_idx]
            placement[v_id] = loc_id
            location_counts[loc_id] += 1
        else:
            # All locations at capacity - use first location
            placement[v_id] = location_ids[0]
            location_counts[location_ids[0]] += 1
    
    return placement


def balanced_proportional_assignment(
    demand: Dict[int, int],
    vehicles: List,
    max_concentration: float = 0.30
) -> Dict[int, int]:
    """
    Simple proportional assignment based on demand.
    Fast and effective for most cases.
    
    Returns:
        {vehicle_id: location_id}
    """
    if not demand:
        return {v.id: 1 for v in vehicles}
    
    # Sort locations by demand
    sorted_locations = sorted(demand.items(), key=lambda x: x[1], reverse=True)
    
    placement = {}
    total_demand = sum(demand.values())
    vehicle_index = 0
    max_per_location = max(1, int(len(vehicles) * max_concentration))
    
    for loc_id, loc_demand in sorted_locations:
        if vehicle_index >= len(vehicles):
            break
        
        # Allocate proportionally
        proportion = loc_demand / total_demand
        vehicles_needed = max(1, int(len(vehicles) * proportion))
        vehicles_needed = min(vehicles_needed, max_per_location)
        vehicles_needed = min(vehicles_needed, len(vehicles) - vehicle_index)
        
        for _ in range(vehicles_needed):
            if vehicle_index >= len(vehicles):
                break
            placement[vehicles[vehicle_index].id] = loc_id
            vehicle_index += 1
    
    # Assign remaining to top location
    if vehicle_index < len(vehicles):
        top_location = sorted_locations[0][0]
        for i in range(vehicle_index, len(vehicles)):
            placement[vehicles[i].id] = top_location
    
    return placement


def calculate_placement_quality(
    placement: Dict[int, int],
    demand: Dict[int, int],
    relation_lookup: Dict,
    config
) -> Dict:
    """
    Evaluate placement quality.
    
    Returns:
        {
            'total_vehicles': int,
            'locations_used': int,
            'max_concentration': float,
            'demand_coverage': float,
            'estimated_relocation_cost': float
        }
    """
    from collections import Counter
    
    location_counts = Counter(placement.values())
    
    # Coverage: how many vehicles at high-demand locations?
    total_demand = sum(demand.values())
    covered_demand = sum(demand.get(loc, 0) * count 
                        for loc, count in location_counts.items())
    coverage = covered_demand / (total_demand * len(placement)) if total_demand > 0 else 0
    
    # Concentration
    max_at_location = max(location_counts.values()) if location_counts else 0
    concentration = max_at_location / len(placement) if placement else 0
    
    # Estimated relocation cost
    # For each location with demand but no vehicles, estimate cost
    estimated_cost = 0.0
    for loc_id, loc_demand in demand.items():
        vehicles_here = location_counts.get(loc_id, 0)
        if loc_demand > vehicles_here:
            # Deficit - will need relocations
            deficit = loc_demand - vehicles_here
            # Assume average relocation cost of 2500 PLN
            estimated_cost += deficit * 2500
    
    return {
        'total_vehicles': len(placement),
        'locations_used': len(location_counts),
        'max_concentration': concentration,
        'demand_coverage': coverage,
        'estimated_relocation_cost': estimated_cost,
        'location_distribution': dict(location_counts)
    }


def optimize_placement(
    vehicles: List,
    routes: List,
    relation_lookup: Dict,
    config,
    strategy: str = 'cost_matrix'
) -> Tuple[Dict[int, int], Dict]:
    """
    Main placement optimization function.
    
    Args:
        vehicles: List of Vehicle objects
        routes: List of Route objects (sorted by date)
        relation_lookup: Location relations
        config: Configuration object
        strategy: 'cost_matrix' or 'proportional'
    
    Returns:
        (placement_dict, quality_metrics)
    """
    # Step 1: Analyze demand
    demand = analyze_demand(routes, config.placement_lookahead_days)
    
    # Step 2: Optimize placement
    if strategy == 'cost_matrix':
        cost_matrix, vehicle_ids, location_ids = build_cost_matrix(
            vehicles, demand, relation_lookup, config
        )
        placement = greedy_min_cost_assignment(
            cost_matrix, vehicle_ids, location_ids
        )
    elif strategy == 'proportional':
        placement = balanced_proportional_assignment(
            demand, vehicles
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    # Step 3: Evaluate quality
    quality = calculate_placement_quality(
        placement, demand, relation_lookup, config
    )
    
    return placement, quality

