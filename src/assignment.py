"""
Route assignment algorithm - Greedy with look-ahead and chaining.
Assigns vehicles to routes minimizing total cost.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from models import (
    Vehicle, Route, VehicleState, RouteAssignment,
    AssignmentConfig, AssignmentResult
)
from constraints import is_feasible, check_service_need
from costs import calculate_assignment_cost, calculate_relocation_cost, calculate_overage_cost
from data_loader import get_relation


def initialize_vehicle_states(
    vehicles: List[Vehicle],
    start_date: datetime,
    config: AssignmentConfig
) -> Dict[int, VehicleState]:
    """
    Create runtime state for each vehicle.
    Vehicles are available 24 hours BEFORE first route to allow initial relocations.
    """
    states = {}
    
    # Make vehicles available 24 hours before first route
    # This allows time for initial positioning/relocation
    available_from = start_date - timedelta(hours=24)
    
    for vehicle in vehicles:
        states[vehicle.id] = VehicleState(
            vehicle_id=vehicle.id,
            current_location_id=vehicle.current_location_id,
            current_odometer_km=vehicle.current_odometer_km,
            km_since_last_service=0,  # Assume just serviced
            km_driven_this_lease_year=0,
            total_lifetime_km=vehicle.current_odometer_km,
            available_from=available_from,  # 24h buffer for initial positioning
            last_route_id=None,
            lease_cycle_number=1,
            lease_start_date=vehicle.leasing_start_date,
            lease_end_date=vehicle.leasing_end_date,
            annual_limit_km=vehicle.annual_limit_km,
            service_interval_km=vehicle.service_interval_km,
            total_contract_limit_km=vehicle.total_contract_limit_km
        )
    
    return states


def build_future_route_chain(
    vehicle_state: VehicleState,
    route: Route,
    all_routes: List[Route],
    route_index: int,
    relation_lookup: Dict,
    config: AssignmentConfig,
    max_depth: int = 3
) -> Tuple[float, List[Route]]:
    """
    Build a chain of future routes this vehicle could complete after this route.
    Returns a score indicating quality of future opportunities.
    
    This is the look-ahead logic - evaluates if assigning this vehicle sets up
    good future assignments.
    """
    if max_depth <= 0 or route_index >= len(all_routes) - 1:
        return 0.0, []
    
    chain_score = 0.0
    chain_routes = []
    
    # Simulate vehicle state after completing this route
    future_state = VehicleState(
        vehicle_id=vehicle_state.vehicle_id,
        current_location_id=route.end_location_id,
        current_odometer_km=vehicle_state.current_odometer_km + int(route.distance_km),
        km_since_last_service=vehicle_state.km_since_last_service + int(route.distance_km),
        km_driven_this_lease_year=vehicle_state.km_driven_this_lease_year + int(route.distance_km),
        total_lifetime_km=vehicle_state.total_lifetime_km + int(route.distance_km),
        available_from=route.end_datetime,
        last_route_id=route.id,
        lease_cycle_number=vehicle_state.lease_cycle_number,
        lease_start_date=vehicle_state.lease_start_date,
        lease_end_date=vehicle_state.lease_end_date,
        annual_limit_km=vehicle_state.annual_limit_km,
        service_interval_km=vehicle_state.service_interval_km,
        total_contract_limit_km=vehicle_state.total_contract_limit_km,
        relocations_in_window=vehicle_state.relocations_in_window.copy()
    )
    
    # Look at next N routes within time window
    look_ahead_end = route.end_datetime + timedelta(days=config.look_ahead_days)
    candidate_routes = []
    
    for i in range(route_index + 1, min(route_index + 50, len(all_routes))):  # Check next 50 routes max
        next_route = all_routes[i]
        
        if next_route.start_datetime > look_ahead_end:
            break
        
        # Check if this route is feasible for future state
        feasible, _ = is_feasible(future_state, next_route, relation_lookup, config, enforce_swap_policy=False)
        
        if feasible:
            # Calculate cost of this future assignment
            cost, _ = calculate_assignment_cost(future_state, next_route, relation_lookup, config)
            
            # Lower cost = better opportunity
            # Score inversely proportional to cost
            if cost < 999999:
                route_score = 1000.0 / (cost + 100.0)  # Avoid division by zero
                candidate_routes.append((route_score, next_route, cost))
    
    # Take best future routes
    candidate_routes.sort(key=lambda x: x[0], reverse=True)
    
    for i, (score, future_route, cost) in enumerate(candidate_routes[:max_depth]):
        # Diminishing weight for routes further ahead
        weight = 0.5 ** i
        chain_score += score * weight
        chain_routes.append(future_route)
    
    return chain_score, chain_routes


def find_best_vehicle_with_lookahead(
    route: Route,
    route_index: int,
    all_routes: List[Route],
    vehicle_states: Dict[int, VehicleState],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> Tuple[Optional[int], float, float]:
    """
    Find best vehicle for this route using greedy + look-ahead.
    
    Returns:
        (vehicle_id, assignment_cost, chain_score)
    """
    best_vehicle = None
    best_score = float('inf')  # Lower is better
    best_cost = float('inf')
    best_chain_score = 0.0
    
    feasible_vehicles = []
    
    # First pass: find all feasible vehicles
    for vehicle_id, state in vehicle_states.items():
        # Check feasibility
        feasible, reason = is_feasible(state, route, relation_lookup, config)
        
        if feasible:
            # Calculate immediate cost
            cost, _ = calculate_assignment_cost(state, route, relation_lookup, config)
            feasible_vehicles.append((vehicle_id, state, cost))
    
    # If no feasible vehicles with strict swap policy, try relaxing it
    if not feasible_vehicles:
        for vehicle_id, state in vehicle_states.items():
            feasible, reason = is_feasible(state, route, relation_lookup, config, enforce_swap_policy=False)
            
            if feasible:
                cost, _ = calculate_assignment_cost(state, route, relation_lookup, config)
                # Add penalty for violating swap policy
                cost += 5000.0
                feasible_vehicles.append((vehicle_id, state, cost))
    
    if not feasible_vehicles:
        return None, float('inf'), 0.0
    
    # Second pass: evaluate with look-ahead
    for vehicle_id, state, immediate_cost in feasible_vehicles:
        # Build future chain
        chain_score, chain_routes = build_future_route_chain(
            state, route, all_routes, route_index,
            relation_lookup, config, config.chain_depth
        )
        
        # Combined score: immediate cost - future opportunity bonus
        # Higher chain_score = better future opportunities = lower effective cost
        effective_cost = immediate_cost - (chain_score * 10.0)  # Weight chain score
        
        if effective_cost < best_score:
            best_score = effective_cost
            best_vehicle = vehicle_id
            best_cost = immediate_cost
            best_chain_score = chain_score
    
    return best_vehicle, best_cost, best_chain_score


def update_vehicle_state(
    vehicle_state: VehicleState,
    route: Route,
    assignment_cost: float,
    relation_lookup: Dict,
    config: AssignmentConfig
) -> None:
    """
    Update vehicle state after route assignment (mutate in place).
    """
    # Check if relocation occurred
    relocation_occurred = vehicle_state.current_location_id != route.start_location_id
    relocation_km = 0
    
    if relocation_occurred:
        reloc_cost, reloc_dist, reloc_time = calculate_relocation_cost(
            vehicle_state.current_location_id,
            route.start_location_id,
            relation_lookup,
            config
        )
        vehicle_state.add_relocation(
            route.start_datetime,
            vehicle_state.current_location_id,
            route.start_location_id,
            reloc_cost
        )
        
        # Add relocation distance to odometer/counters
        relocation_km = int(reloc_dist)
        vehicle_state.current_odometer_km += relocation_km
        vehicle_state.km_driven_this_lease_year += relocation_km
        vehicle_state.total_lifetime_km += relocation_km
        vehicle_state.km_since_last_service += relocation_km
    
    # Update location
    vehicle_state.current_location_id = route.end_location_id
    
    # Update mileage counters (route distance)
    distance = int(route.distance_km)
    vehicle_state.current_odometer_km += distance
    vehicle_state.km_driven_this_lease_year += distance
    vehicle_state.total_lifetime_km += distance
    vehicle_state.km_since_last_service += distance
    
    # Update availability
    vehicle_state.available_from = route.end_datetime
    vehicle_state.last_route_id = route.id
    vehicle_state.routes_completed += 1
    
    # Update overage cost
    overage_cost, _ = calculate_overage_cost(
        vehicle_state.km_driven_this_lease_year,
        vehicle_state.annual_limit_km,
        config
    )
    vehicle_state.total_overage_cost = overage_cost


def create_route_assignment(
    route: Route,
    vehicle_id: int,
    vehicle_state_before: VehicleState,
    vehicle_state_after: VehicleState,
    assignment_cost: float,
    chain_score: float,
    relation_lookup: Dict,
    config: AssignmentConfig
) -> RouteAssignment:
    """
    Create assignment record with full details.
    """
    requires_relocation = vehicle_state_before.current_location_id != route.start_location_id
    requires_service, _ = check_service_need(vehicle_state_after, route, config)
    
    reloc_dist = 0.0
    reloc_time = 0.0
    reloc_from = None
    reloc_to = None
    
    if requires_relocation:
        reloc_from = vehicle_state_before.current_location_id
        reloc_to = route.start_location_id
        _, reloc_dist, reloc_time = calculate_relocation_cost(
            reloc_from, reloc_to, relation_lookup, config
        )
    
    overage_km = max(0, vehicle_state_after.km_driven_this_lease_year - vehicle_state_after.annual_limit_km)
    
    return RouteAssignment(
        route_id=route.id,
        vehicle_id=vehicle_id,
        date=route.start_datetime,
        route_distance_km=route.distance_km,
        route_start_location=route.start_location_id,
        route_end_location=route.end_location_id,
        vehicle_km_before=vehicle_state_before.current_odometer_km,
        vehicle_km_after=vehicle_state_after.current_odometer_km,
        annual_km_before=vehicle_state_before.km_driven_this_lease_year,
        annual_km_after=vehicle_state_after.km_driven_this_lease_year,
        requires_relocation=requires_relocation,
        requires_service=requires_service,
        assignment_cost=assignment_cost,
        relocation_from=reloc_from,
        relocation_to=reloc_to,
        relocation_distance=reloc_dist,
        relocation_time=reloc_time,
        overage_km=overage_km,
        chain_score=chain_score
    )


def assign_routes(
    vehicles: List[Vehicle],
    routes: List[Route],
    relation_lookup: Dict,
    config: AssignmentConfig
) -> AssignmentResult:
    """
    Main assignment algorithm - greedy with look-ahead and chaining.
    """
    print("\n" + "="*60)
    print("ASSIGNMENT ALGORITHM - Greedy with Look-Ahead & Chaining")
    print("="*60)
    print(f"\n[*] Configuration:")
    print(f"    Look-ahead days: {config.look_ahead_days}")
    print(f"    Chain depth: {config.chain_depth}")
    print(f"    Swap period: {config.swap_period_days} days")
    print(f"    Service tolerance: {config.service_tolerance_km} km")
    
    # Initialize vehicle states
    start_date = routes[0].start_datetime if routes else datetime.now()
    vehicle_states = initialize_vehicle_states(vehicles, start_date, config)
    
    print(f"\n[*] Initialized {len(vehicle_states)} vehicle states")
    print(f"[*] Processing {len(routes)} routes...")
    print(f"[*] Period: {routes[0].start_datetime.date()} to {routes[-1].start_datetime.date()}\n")
    
    assignments = []
    unassigned_routes = []
    
    # Process routes day by day
    current_day = None
    day_count = 0
    routes_processed = 0
    
    for route_index, route in enumerate(routes):
        # Progress reporting
        route_day = route.start_datetime.date()
        if route_day != current_day:
            current_day = route_day
            day_count += 1
            
            if day_count % 30 == 0:
                print(f"[*] Progress: Day {day_count} ({current_day}) - {routes_processed} routes assigned")
        
        # Find best vehicle with look-ahead
        vehicle_id, cost, chain_score = find_best_vehicle_with_lookahead(
            route, route_index, routes, vehicle_states,
            relation_lookup, config
        )
        
        if vehicle_id is None:
            print(f"⚠️  WARNING: No feasible vehicle for route {route.id} on {route.start_datetime}")
            unassigned_routes.append(route)
            continue
        
        # Capture state before update
        state_before = VehicleState(**vars(vehicle_states[vehicle_id]))
        
        # Update vehicle state
        update_vehicle_state(vehicle_states[vehicle_id], route, cost, relation_lookup, config)
        
        # Create assignment record
        assignment = create_route_assignment(
            route, vehicle_id,
            state_before, vehicle_states[vehicle_id],
            cost, chain_score,
            relation_lookup, config
        )
        assignments.append(assignment)
        routes_processed += 1
    
    # Calculate totals
    total_relocation_cost = sum(s.total_relocation_cost for s in vehicle_states.values())
    total_overage_cost = sum(s.total_overage_cost for s in vehicle_states.values())
    total_cost = total_relocation_cost + total_overage_cost
    avg_cost = total_cost / len(assignments) if assignments else 0
    
    print(f"\n[*] Assignment Complete!")
    print(f"    Routes assigned: {len(assignments)}")
    print(f"    Routes unassigned: {len(unassigned_routes)}")
    print(f"    Total relocations: {sum(s.total_relocations for s in vehicle_states.values())}")
    print(f"    Total cost: {total_cost:,.2f} PLN")
    print(f"      - Relocation cost: {total_relocation_cost:,.2f} PLN")
    print(f"      - Overage cost: {total_overage_cost:,.2f} PLN")
    print(f"    Avg cost per route: {avg_cost:.2f} PLN")
    
    # Vehicle statistics
    vehicles_over_limit = sum(1 for s in vehicle_states.values() 
                             if s.km_driven_this_lease_year > s.annual_limit_km)
    print(f"\n[*] Vehicle Statistics:")
    print(f"    Vehicles over annual limit: {vehicles_over_limit}/{len(vehicles)}")
    
    if vehicles_over_limit > 0:
        avg_overage = sum(max(0, s.km_driven_this_lease_year - s.annual_limit_km) 
                         for s in vehicle_states.values()) / vehicles_over_limit
        print(f"    Avg overage per violating vehicle: {avg_overage:.0f} km")
    
    print("\n" + "="*60)
    print("ASSIGNMENT COMPLETE")
    print("="*60 + "\n")
    
    return AssignmentResult(
        assignments=assignments,
        vehicle_states=vehicle_states,
        total_cost=total_cost,
        total_relocation_cost=total_relocation_cost,
        total_overage_cost=total_overage_cost,
        routes_assigned=len(assignments),
        routes_unassigned=len(unassigned_routes),
        avg_cost_per_route=avg_cost
    )

