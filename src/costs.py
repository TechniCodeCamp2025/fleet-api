"""
Cost calculation functions for fleet optimization.
"""
from typing import Optional
from models import VehicleState, Route, AssignmentConfig, LocationRelation
from data_loader import get_relation


def calculate_relocation_cost(
    from_loc: int,
    to_loc: int,
    relation_lookup: dict,
    config: AssignmentConfig
) -> tuple[float, float, float]:
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
    time_cost = relation.time * config.relocation_per_hour_pln
    
    total_cost = base_cost + distance_cost + time_cost
    
    return total_cost, relation.dist, relation.time


def calculate_overage_cost(
    km_driven_this_year: int,
    annual_limit_km: int,
    config: AssignmentConfig
) -> tuple[float, int]:
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
    relation_lookup: dict,
    config: AssignmentConfig,
    look_ahead_bonus: float = 0.0
) -> tuple[float, dict]:
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
    placements: dict,
    routes: list,
    relation_lookup: dict,
    config: AssignmentConfig,
    lookahead_days: int = 14
) -> float:
    """
    Estimate total relocation cost for initial placement.
    Used to evaluate placement quality.
    """
    from datetime import timedelta
    
    if not routes:
        return 0.0
    
    # Get first N days of routes
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    early_routes = [r for r in routes if r.start_datetime < end_date]
    
    # Count relocations needed
    placement_costs = []
    location_by_vehicle = {v_id: loc_id for v_id, loc_id in placements.items()}
    
    # Simple estimation: assume uniform distribution of routes to vehicles
    for route in early_routes:
        if route.start_location_id:
            # Find closest vehicle location
            min_cost = float('inf')
            for v_id, v_loc in location_by_vehicle.items():
                cost, _, _ = calculate_relocation_cost(
                    v_loc,
                    route.start_location_id,
                    relation_lookup,
                    config
                )
                if cost < min_cost:
                    min_cost = cost
            
            if min_cost < 999999:
                placement_costs.append(min_cost)
    
    return sum(placement_costs)

