"""
Constraint validation functions.
"""
from datetime import timedelta
from typing import Optional, Tuple, Dict
from models import VehicleState, Route, AssignmentConfig
from data_loader import get_relation


def is_time_feasible(
    vehicle_state: VehicleState,
    route: Route,
    relation_lookup: Dict
) -> Tuple[bool, str]:
    """
    Check if vehicle can reach route start on time.
    
    Returns:
        (is_feasible, reason)
    """
    # Vehicle must be available
    if vehicle_state.available_from > route.start_datetime:
        time_diff = (vehicle_state.available_from - route.start_datetime).total_seconds() / 3600
        return False, f"Vehicle available at {vehicle_state.available_from}, route starts {route.start_datetime} ({time_diff:.1f}h too late)"
    
    # If relocation needed, check travel time
    if vehicle_state.current_location_id != route.start_location_id:
        relation = get_relation(
            vehicle_state.current_location_id,
            route.start_location_id,
            relation_lookup
        )
        
        if not relation:
            return False, f"No route from location {vehicle_state.current_location_id} to {route.start_location_id}"
        
        # Calculate arrival time
        travel_time = timedelta(minutes=relation.time)
        arrival = vehicle_state.available_from + travel_time
        
        if arrival > route.start_datetime:
            shortfall = (arrival - route.start_datetime).total_seconds() / 3600
            return False, f"Cannot reach in time (arrives {shortfall:.1f}h late)"
    
    return True, "OK"


def check_service_need(
    vehicle_state: VehicleState,
    route: Route,
    config: AssignmentConfig
) -> Tuple[bool, int]:
    """
    Check if vehicle needs service before/after route.
    
    Returns:
        (needs_service, km_after_route)
    """
    km_after = vehicle_state.km_since_last_service + int(route.distance_km)
    needs = km_after > (vehicle_state.service_interval_km + config.service_tolerance_km)
    
    return needs, km_after


def check_contract_limit(
    vehicle_state: VehicleState,
    route: Route
) -> Tuple[bool, int]:
    """
    Check if route would violate lifetime contract limit (HARD constraint).
    
    Returns:
        (violates, future_km)
    """
    if vehicle_state.total_contract_limit_km is None:
        return False, vehicle_state.total_lifetime_km + int(route.distance_km)
    
    future_km = vehicle_state.total_lifetime_km + int(route.distance_km)
    violates = future_km > vehicle_state.total_contract_limit_km
    
    return violates, future_km


def check_swap_policy(
    vehicle_state: VehicleState,
    route: Route,
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Tuple[bool, int]:
    """
    Check if assigning this route would violate swap policy.
    
    Returns:
        (requires_swap, days_since_last_swap)
    """
    # No swap needed if at same location
    if vehicle_state.current_location_id == route.start_location_id:
        return False, 999
    
    # Check relation exists
    relation = get_relation(
        vehicle_state.current_location_id,
        route.start_location_id,
        relation_lookup
    )
    if not relation:
        return True, 0  # Would need swap but no path
    
    # Check if can swap
    can_swap = vehicle_state.can_swap_at(route.start_datetime, config.swap_period_days)
    
    # Calculate days since last swap
    if vehicle_state.relocations_in_window:
        last_swap_date = vehicle_state.relocations_in_window[-1][0]
        days_since = (route.start_datetime - last_swap_date).days
    else:
        days_since = 999
    
    return not can_swap, days_since


def is_feasible(
    vehicle_state: VehicleState,
    route: Route,
    relation_lookup: Dict,
    config: AssignmentConfig,
    enforce_swap_policy: bool = True
) -> Tuple[bool, str]:
    """
    Comprehensive feasibility check.
    
    Returns:
        (is_feasible, reason)
    """
    # 1. HARD: Time feasibility
    time_ok, reason = is_time_feasible(vehicle_state, route, relation_lookup)
    if not time_ok:
        return False, f"Time: {reason}"
    
    # 2. HARD: Contract limit
    violates_limit, future_km = check_contract_limit(vehicle_state, route)
    if violates_limit:
        return False, f"Contract limit: would reach {future_km} km (limit: {vehicle_state.total_contract_limit_km})"
    
    # 3. HARD: Swap policy (if enforced)
    if enforce_swap_policy:
        requires_swap, days_since = check_swap_policy(
            vehicle_state, route, relation_lookup, config
        )
        if requires_swap and days_since < config.swap_period_days:
            return False, f"Swap policy: last swap {days_since} days ago (requires {config.swap_period_days})"
    
    # Soft constraints (service) handled via cost penalties
    return True, "OK"


def validate_assignment(
    vehicle_state: VehicleState,
    route: Route,
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Dict:
    """
    Validate assignment and return detailed status.
    """
    status = {
        'feasible': False,
        'time_ok': False,
        'contract_ok': False,
        'swap_ok': False,
        'service_ok': True,
        'reasons': []
    }
    
    # Time check
    time_ok, time_reason = is_time_feasible(vehicle_state, route, relation_lookup)
    status['time_ok'] = time_ok
    if not time_ok:
        status['reasons'].append(time_reason)
    
    # Contract check
    violates, _ = check_contract_limit(vehicle_state, route)
    status['contract_ok'] = not violates
    if violates:
        status['reasons'].append("Contract limit violation")
    
    # Swap check
    requires_swap, days = check_swap_policy(vehicle_state, route, relation_lookup, config)
    status['swap_ok'] = not requires_swap
    if requires_swap:
        status['reasons'].append(f"Swap too soon ({days} days)")
    
    # Service check (soft)
    needs_service, _ = check_service_need(vehicle_state, route, config)
    status['service_ok'] = not needs_service
    if needs_service:
        status['reasons'].append("Service needed soon")
    
    # Overall feasibility
    status['feasible'] = time_ok and status['contract_ok'] and status['swap_ok']
    
    return status

