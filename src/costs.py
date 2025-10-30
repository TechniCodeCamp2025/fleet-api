"""
Cost calculation functions for fleet optimization.
"""
from typing import Optional, Tuple, Dict, List
from models import VehicleState, Route, AssignmentConfig
from data_loader import get_relation


def calculate_relocation_cost(
    from_loc: int,
    to_loc: int,
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Tuple[float, float, float]:
    """
    Calculate cost to relocate vehicle between locations.
    
    Returns:
        (total_cost, distance_km, time_hours)
    """
    # Same location = no relocation
    if from_loc == to_loc:
        return 0.0, 0.0, 0.0
    
    # Get relation
    relation = get_relation(from_loc, to_loc, relation_lookup)
    
    if not relation:
        # No path available - return very high cost
        return 999999.0, 0.0, 0.0
    
    # Calculate cost components
    base_cost = config.relocation_base_cost_pln
    distance_cost = relation.dist * config.relocation_per_km_pln
    # relation.time is in minutes, convert to hours for cost calculation
    time_cost = (relation.time / 60.0) * config.relocation_per_hour_pln
    
    total_cost = base_cost + distance_cost + time_cost
    
    return total_cost, relation.dist, relation.time


def calculate_overage_cost(
    km_driven_this_year: int,
    annual_limit_km: int,
    config: AssignmentConfig
) -> Tuple[float, int]:
    """
    Calculate overage cost if annual limit exceeded.
    
    Returns:
        (overage_cost, overage_km)
    """
    if km_driven_this_year <= annual_limit_km:
        return 0.0, 0
    
    overage_km = km_driven_this_year - annual_limit_km
    overage_cost = overage_km * config.overage_per_km_pln
    
    return overage_cost, overage_km


def calculate_assignment_cost(
    vehicle_state: VehicleState,
    route: Route,
    relation_lookup: Dict,
    config: AssignmentConfig,
    look_ahead_bonus: float = 0.0
) -> Tuple[float, Dict]:
    """
    Calculate total cost of assigning vehicle to route.
    
    Returns:
        (total_cost, cost_breakdown)
    """
    cost_breakdown = {
        'relocation': 0.0,
        'overage': 0.0,
        'service_penalty': 0.0,
        'look_ahead_bonus': look_ahead_bonus
    }
    
    # 1. Relocation cost
    if vehicle_state.current_location_id != route.start_location_id:
        reloc_cost, _, _ = calculate_relocation_cost(
            vehicle_state.current_location_id,
            route.start_location_id,
            relation_lookup,
            config
        )
        cost_breakdown['relocation'] = reloc_cost
    
    # 2. Overage cost (project future state)
    future_annual_km = vehicle_state.km_driven_this_lease_year + int(route.distance_km)
    overage_cost, _ = calculate_overage_cost(
        future_annual_km,
        vehicle_state.annual_limit_km,
        config
    )
    cost_breakdown['overage'] = overage_cost
    
    # 3. Service penalty (soft constraint)
    if vehicle_state.needs_service(config.service_tolerance_km):
        cost_breakdown['service_penalty'] = config.service_penalty_pln
    
    # Calculate total
    total_cost = sum(cost_breakdown.values())
    
    return total_cost, cost_breakdown


def calculate_placement_cost(
    placements: Dict,
    routes: List,
    relation_lookup: Dict,
    config: AssignmentConfig,
    lookahead_days: int = 14
) -> float:
    """
    Estimate total relocation cost for initial placement.
    Used to evaluate placement quality.
    
    OPTIMIZED: Uses location-based heuristic instead of checking every vehicle.
    """
    from datetime import timedelta
    from collections import Counter
    
    if not routes:
        return 0.0
    
    # Get first N days of routes
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    early_routes = [r for r in routes if r.start_datetime < end_date]
    
    # Count vehicles at each location
    location_vehicle_counts = Counter(placements.values())
    
    # Count demand at each location
    location_demand = Counter(r.start_location_id for r in early_routes if r.start_location_id)
    
    # OPTIMIZATION: Only calculate cost for locations with demand mismatch
    # Cache location-to-location costs to avoid recalculation
    location_cost_cache = {}
    
    total_cost = 0.0
    
    for demand_loc, demand_count in location_demand.items():
        vehicles_here = location_vehicle_counts.get(demand_loc, 0)
        
        if vehicles_here >= demand_count:
            # Enough vehicles here, no relocations needed (optimistic)
            continue
        
        # Need relocations - find cheapest source location
        shortage = demand_count - vehicles_here
        
        # Find nearest location with spare vehicles
        min_reloc_cost = float('inf')
        
        for source_loc, vehicle_count in location_vehicle_counts.items():
            if source_loc == demand_loc:
                continue
            
            # Check if this location has spare vehicles
            source_demand = location_demand.get(source_loc, 0)
            if vehicle_count <= source_demand:
                continue  # No spare vehicles
            
            # Check cache first
            cache_key = (source_loc, demand_loc)
            if cache_key in location_cost_cache:
                reloc_cost = location_cost_cache[cache_key]
            else:
                reloc_cost, _, _ = calculate_relocation_cost(
                    source_loc,
                    demand_loc,
                    relation_lookup,
                    config
                )
                location_cost_cache[cache_key] = reloc_cost
            
            if reloc_cost < min_reloc_cost:
                min_reloc_cost = reloc_cost
        
        # Add cost for shortage
        if min_reloc_cost < 999999:
            total_cost += shortage * min_reloc_cost
        else:
            # No path found, use high estimate
            total_cost += shortage * 5000
    
    return total_cost

