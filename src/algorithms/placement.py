"""
Core placement algorithm - pure logic, no I/O.
Determines optimal initial vehicle placement to minimize relocation costs.

IMPROVEMENTS:
- Added route flow analysis (considers both starts AND ends)
- Better demand calculation accounting for vehicle accumulation
"""
from typing import List, Dict, Tuple
from datetime import timedelta
from collections import defaultdict
import numpy as np


def analyze_demand(routes: List, lookahead_days: int = 14) -> Dict[int, int]:
    """
    Count routes starting at each location.
    Note: routes should already be filtered to the lookahead window.
    
    DEPRECATED: Use analyze_route_flow() instead for better results.
    Kept for backward compatibility.
    
    Returns:
        {location_id: route_count}
    """
    demand = defaultdict(int)
    
    if not routes:
        return dict(demand)
    
    for route in routes:
        if route.start_location_id:
            demand[route.start_location_id] += 1
    
    return dict(demand)


def analyze_route_flow(routes: List, lookahead_days: int = 14) -> Dict[str, Dict[int, int]]:
    """
    Analyze route flow patterns considering both starts and ends.
    This gives a better picture of where vehicles are needed vs where they accumulate.
    
    Args:
        routes: List of Route objects (should be filtered to lookahead window)
        lookahead_days: Days to analyze (for metadata)
    
    Returns:
        {
            'starts': {location_id: count},  # Routes starting here (need vehicles)
            'ends': {location_id: count},    # Routes ending here (vehicles accumulate)
            'net_demand': {location_id: net}, # starts - ends (positive = need vehicles)
            'total_activity': {location_id: total} # starts + ends (busy locations)
        }
    """
    starts = defaultdict(int)
    ends = defaultdict(int)
    
    if not routes:
        return {
            'starts': {},
            'ends': {},
            'net_demand': {},
            'total_activity': {}
        }
    
    for route in routes:
        if route.start_location_id:
            starts[route.start_location_id] += 1
        if route.end_location_id:
            ends[route.end_location_id] += 1
    
    # Calculate net demand (positive = need more vehicles, negative = vehicles accumulate)
    all_locations = set(starts.keys()) | set(ends.keys())
    net_demand = {}
    total_activity = {}
    
    for loc_id in all_locations:
        start_count = starts.get(loc_id, 0)
        end_count = ends.get(loc_id, 0)
        net_demand[loc_id] = start_count - end_count
        total_activity[loc_id] = start_count + end_count
    
    return {
        'starts': dict(starts),
        'ends': dict(ends),
        'net_demand': dict(net_demand),
        'total_activity': dict(total_activity)
    }


def build_cost_matrix(
    vehicles: List,
    demand: Dict[int, int],
    relation_lookup: Dict,
    config,
    flow_data: Dict = None
) -> Tuple[np.ndarray, List[int], List[int]]:
    """
    Build cost matrix for vehicle-location assignments.
    
    Cost[i, j] = cost of placing vehicle i at location j
    
    Cost calculation (improved):
    - High total activity (starts + ends): lower cost (busy location)
    - Positive net demand (more starts than ends): lower cost (vehicles needed)
    - Good connectivity: lower cost (can reach other locations)
    
    Args:
        vehicles: List of Vehicle objects
        demand: Legacy demand dict (for backward compatibility)
        relation_lookup: Location relations
        config: Configuration
        flow_data: Optional flow analysis data (from analyze_route_flow)
    
    Returns:
        (cost_matrix, vehicle_ids, location_ids)
    """
    # Use flow data if available, otherwise fall back to simple demand
    if flow_data and flow_data.get('total_activity'):
        activity = flow_data['total_activity']
        net_demand = flow_data.get('net_demand', {})
    elif demand:
        activity = demand
        net_demand = demand  # Treat all demand as net positive
    else:
        # No data - uniform cost
        locations = [1]  # Fallback location
        n_vehicles = len(vehicles)
        n_locations = 1
        cost_matrix = np.ones((n_vehicles, n_locations)) * 1000
        return cost_matrix, [v.id for v in vehicles], locations
    
    # Get candidate locations (those with activity)
    locations = sorted(activity.keys())
    n_vehicles = len(vehicles)
    n_locations = len(locations)
    
    # Initialize cost matrix
    cost_matrix = np.zeros((n_vehicles, n_locations))
    
    # Calculate cost for each vehicle-location pair
    for i, vehicle in enumerate(vehicles):
        for j, loc_id in enumerate(locations):
            # Base cost inversely proportional to activity
            # High activity = low cost (busy location, good to have vehicles)
            local_activity = activity[loc_id]
            # Use logarithmic scaling to avoid extreme differences
            base_cost = 1000 * (1.0 / np.log(local_activity + 2))
            
            # Net demand bonus: prefer locations that need vehicles (more starts than ends)
            local_net_demand = net_demand.get(loc_id, 0)
            if local_net_demand > 0:
                # Positive net demand = need vehicles here
                # Higher net demand = bigger discount
                net_demand_bonus = -min(200, local_net_demand * 10)
            elif local_net_demand < 0:
                # Negative net demand = vehicles accumulate here
                # Apply small penalty (vehicles will end up here anyway)
                net_demand_bonus = min(100, abs(local_net_demand) * 5)
            else:
                net_demand_bonus = 0
            
            # Calculate connectivity bonus
            # Well-connected locations get meaningful discount (increased from 100 to 300)
            connectivity_bonus = 0
            other_locations = [l for l in locations if l != loc_id]
            
            if other_locations and len(other_locations) >= 5:
                connected_count = 0
                check_count = min(20, len(other_locations))
                for other_loc in other_locations[:check_count]:
                    # Check if path exists
                    if (loc_id, other_loc) in relation_lookup or (other_loc, loc_id) in relation_lookup:
                        connected_count += 1
                
                # Bonus if well-connected (20-30% of base cost now)
                connectivity_ratio = connected_count / check_count
                if connectivity_ratio > 0.5:
                    connectivity_bonus = -300 * connectivity_ratio
            
            # Total cost
            cost_matrix[i, j] = base_cost + net_demand_bonus + connectivity_bonus
    
    return cost_matrix, [v.id for v in vehicles], locations


def greedy_min_cost_assignment(
    cost_matrix: np.ndarray,
    vehicle_ids: List[int],
    location_ids: List[int],
    max_per_location: int = None,
    max_concentration: float = 0.30
) -> Dict[int, int]:
    """
    Pure cost-driven greedy assignment with soft concentration penalty.
    
    Strategy:
    - Assign each vehicle to minimize total cost
    - Apply increasing penalty for over-concentration at single locations
    - Let demand naturally guide distribution
    
    Returns:
        {vehicle_id: location_id}
    """
    n_vehicles, n_locations = cost_matrix.shape
    
    if n_locations == 0:
        return {vid: 1 for vid in vehicle_ids}  # Fallback
    
    # Soft cap - will apply penalty, not hard block
    if max_per_location is None:
        max_per_location = max(5, int(n_vehicles * max_concentration))
    
    placement = {}
    location_counts = defaultdict(int)
    
    # Process vehicles in order (simple 0 to n)
    for i in range(n_vehicles):
        v_id = vehicle_ids[i]
        best_loc_idx = None
        best_adjusted_cost = float('inf')
        
        for l_idx in range(n_locations):
            loc_id = location_ids[l_idx]
            
            # Base cost from cost matrix
            base_cost = cost_matrix[i, l_idx]
            
            # Soft concentration penalty
            # As location fills up, gradually increase cost
            current_count = location_counts[loc_id]
            concentration_penalty = 0.0
            
            if current_count >= max_per_location:
                # Strong penalty for exceeding soft limit
                excess = current_count - max_per_location + 1
                concentration_penalty = 5000 * (excess ** 1.5)
            elif current_count > max_per_location * 0.7:
                # Gentle penalty as we approach limit
                ratio = current_count / max_per_location
                concentration_penalty = 1000 * ((ratio - 0.7) / 0.3) ** 2
            
            # Total adjusted cost
            adjusted_cost = base_cost + concentration_penalty
            
            if adjusted_cost < best_adjusted_cost:
                best_adjusted_cost = adjusted_cost
                best_loc_idx = l_idx
        
        # Assign to best location
        if best_loc_idx is not None:
            loc_id = location_ids[best_loc_idx]
            placement[v_id] = loc_id
            location_counts[loc_id] += 1
    
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
    
    # Coverage: percentage of vehicles placed at locations with demand
    locations_with_demand = set(demand.keys())
    vehicles_at_demand_locations = sum(count for loc, count in location_counts.items() 
                                      if loc in locations_with_demand)
    coverage = vehicles_at_demand_locations / len(placement) if placement else 0
    
    # Demand satisfaction: how well does vehicle distribution match demand distribution
    total_demand = sum(demand.values())
    if total_demand > 0:
        demand_satisfaction = 0.0
        for loc, count in location_counts.items():
            if loc in demand:
                # What % of demand is at this location vs % of vehicles
                demand_ratio = demand[loc] / total_demand
                vehicle_ratio = count / len(placement)
                # Perfect match = 1.0, poor match approaches 0
                demand_satisfaction += min(demand_ratio, vehicle_ratio)
    else:
        demand_satisfaction = 0.0
    
    # Concentration
    max_at_location = max(location_counts.values()) if location_counts else 0
    concentration = max_at_location / len(placement) if placement else 0
    
    # Estimated relocation cost
    # Better estimate: only count locations with NO vehicles at all
    # Locations with some vehicles can handle nearby routes efficiently
    estimated_cost = 0.0
    for loc_id, loc_demand in demand.items():
        vehicles_here = location_counts.get(loc_id, 0)
        if vehicles_here == 0:
            # No vehicles at this location - will need relocations
            # Use lower average since nearby locations likely have vehicles
            estimated_cost += loc_demand * 1500
    
    return {
        'total_vehicles': len(placement),
        'locations_used': len(location_counts),
        'max_concentration': concentration,
        'demand_coverage': coverage,
        'demand_satisfaction': demand_satisfaction,
        'estimated_relocation_cost': estimated_cost,
        'location_distribution': dict(location_counts)
    }


def coverage_first_assignment(
    vehicles: List,
    demand: Dict[int, int],
    max_concentration: float = 0.30
) -> Dict[int, int]:
    """
    Coverage-first assignment: ensure ALL locations with demand get at least 1 vehicle,
    then distribute remaining vehicles proportionally to demand.
    
    This guarantees that every location with routes can be serviced.
    
    Returns:
        {vehicle_id: location_id}
    """
    if not demand:
        return {v.id: 1 for v in vehicles}
    
    n_vehicles = len(vehicles)
    n_locations = len(demand)
    
    # Sort locations by demand
    sorted_locations = sorted(demand.items(), key=lambda x: x[1], reverse=True)
    
    placement = {}
    location_counts = defaultdict(int)
    vehicle_index = 0
    
    # Phase 1: Ensure minimum coverage - at least 1 vehicle per location
    # But only if we have enough vehicles
    if n_locations <= n_vehicles:
        print(f"[Placement] Phase 1: Distributing 1 vehicle to each of {n_locations} locations")
        for loc_id, _ in sorted_locations:
            if vehicle_index >= n_vehicles:
                break
            placement[vehicles[vehicle_index].id] = loc_id
            location_counts[loc_id] += 1
            vehicle_index += 1
    else:
        # Too many locations, prioritize high-demand ones
        high_priority = min(n_vehicles // 2, n_locations)
        print(f"[Placement] Phase 1: Covering top {high_priority} high-demand locations")
        for loc_id, _ in sorted_locations[:high_priority]:
            if vehicle_index >= n_vehicles:
                break
            placement[vehicles[vehicle_index].id] = loc_id
            location_counts[loc_id] += 1
            vehicle_index += 1
    
    # Phase 2: Distribute remaining vehicles proportionally to demand
    remaining = n_vehicles - vehicle_index
    if remaining > 0:
        print(f"[Placement] Phase 2: Distributing {remaining} remaining vehicles proportionally")
        total_demand = sum(demand.values())
        max_per_location = max(3, int(n_vehicles * max_concentration))
        
        for loc_id, loc_demand in sorted_locations:
            if vehicle_index >= n_vehicles:
                break
            
            # Calculate proportional share (minus the 1 already placed)
            proportion = loc_demand / total_demand
            target_count = max(1, int(n_vehicles * proportion))
            
            # Respect concentration limit
            target_count = min(target_count, max_per_location)
            
            # Place additional vehicles up to target
            current_count = location_counts[loc_id]
            to_place = min(target_count - current_count, remaining)
            to_place = max(0, to_place)  # Don't place negative
            
            for _ in range(to_place):
                if vehicle_index >= n_vehicles:
                    break
                placement[vehicles[vehicle_index].id] = loc_id
                location_counts[loc_id] += 1
                vehicle_index += 1
                remaining -= 1
    
    # Phase 3: Assign any stragglers to top locations
    if vehicle_index < n_vehicles:
        print(f"[Placement] Phase 3: Assigning {n_vehicles - vehicle_index} remaining to top locations")
        while vehicle_index < n_vehicles:
            top_location = sorted_locations[0][0]
            placement[vehicles[vehicle_index].id] = top_location
            location_counts[top_location] += 1
            vehicle_index += 1
    
    print(f"[Placement] Final: {len(location_counts)} locations used, "
          f"max {max(location_counts.values())} vehicles at one location")
    
    return placement


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
        routes: ALL routes (will be filtered to lookahead window)
        relation_lookup: Location relations
        config: Configuration object
        strategy: 'cost_matrix', 'proportional', or 'coverage_first'
    
    Returns:
        (placement_dict, quality_metrics)
    """
    # Filter routes to lookahead window
    lookahead_routes = routes
    if routes and config.placement_lookahead_days > 0:
        start_date = routes[0].start_datetime
        end_date = start_date + timedelta(days=config.placement_lookahead_days)
        lookahead_routes = [r for r in routes if r.start_datetime < end_date]
    
    # Step 1: Analyze route flow (both starts and ends)
    flow_data = analyze_route_flow(lookahead_routes, config.placement_lookahead_days)
    
    # Also keep simple demand for backward compatibility
    demand = flow_data['starts'] if flow_data['starts'] else analyze_demand(lookahead_routes, config.placement_lookahead_days)
    
    # Step 2: Optimize placement
    if strategy == 'coverage_first':
        # NEW: Coverage-first strategy for maximum feasibility
        placement = coverage_first_assignment(
            vehicles, demand,
            max_concentration=config.placement_max_concentration
        )
    elif strategy == 'cost_matrix':
        cost_matrix, vehicle_ids, location_ids = build_cost_matrix(
            vehicles, demand, relation_lookup, config, flow_data=flow_data
        )
        placement = greedy_min_cost_assignment(
            cost_matrix, vehicle_ids, location_ids,
            max_per_location=config.placement_max_vehicles_per_location,
            max_concentration=config.placement_max_concentration
        )
    elif strategy == 'proportional':
        # Use total activity for proportional (busier locations get more vehicles)
        activity = flow_data['total_activity'] if flow_data['total_activity'] else demand
        placement = balanced_proportional_assignment(
            activity, vehicles,
            max_concentration=config.placement_max_concentration
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    # Step 3: Evaluate quality
    quality = calculate_placement_quality(
        placement, demand, relation_lookup, config
    )
    
    # Add metadata including flow analysis
    quality['lookahead_routes_analyzed'] = len(lookahead_routes)
    quality['strategy_used'] = strategy
    quality['flow_analysis'] = {
        'total_starts': sum(flow_data['starts'].values()),
        'total_ends': sum(flow_data['ends'].values()),
        'locations_with_net_demand': sum(1 for v in flow_data['net_demand'].values() if v > 0),
        'locations_with_accumulation': sum(1 for v in flow_data['net_demand'].values() if v < 0)
    }
    
    return placement, quality