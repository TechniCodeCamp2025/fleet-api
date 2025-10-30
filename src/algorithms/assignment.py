"""
Core assignment algorithm - pure logic, no I/O.
Assigns vehicles to routes minimizing total cost while respecting constraints.

IMPROVEMENTS FROM REVIEW:
- Removed chain building by default (spec compliance)
- Implemented actual service scheduling
- Fixed annual lease cycle reset
- Added relation caching
- Optimized swap policy checks
- Replaced magic numbers with constants/config
- Added validation and better error handling
- Added progress reporting
- Fixed service timing consistency
- Added workload balancing
- Extracted relation lookup helper
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from functools import lru_cache
from copy import deepcopy
from collections import defaultdict
from rich.console import Console

from .relation_helper import (
    get_cached_relation,
    calculate_relocation_cost,
    get_relocation_info,
    create_relation_cache
)

console = Console()

# Constants
INFEASIBLE_COST = float('inf')
INITIAL_AVAILABILITY_HOURS = 24  # Hours before start date vehicles are available


def initialize_states(vehicles: List, start_date: datetime) -> Dict:
    """
    Initialize vehicle states for simulation.
    Available INITIAL_AVAILABILITY_HOURS before start to allow initial positioning.
    """
    states = {}
    available_from = start_date - timedelta(hours=INITIAL_AVAILABILITY_HOURS)
    
    for vehicle in vehicles:
        states[vehicle.id] = {
            'vehicle_id': vehicle.id,
            'current_location_id': vehicle.current_location_id,
            'current_odometer_km': vehicle.current_odometer_km,
            'km_since_last_service': 0,  # Assume just serviced
            'km_driven_this_lease_year': 0,
            'total_lifetime_km': vehicle.current_odometer_km,
            'available_from': available_from,
            'last_route_id': None,
            'relocations': [],  # Rolling window of recent relocations
            'annual_limit_km': vehicle.annual_limit_km,
            'service_interval_km': vehicle.service_interval_km,
            'total_contract_limit_km': vehicle.total_contract_limit_km,
            'lease_start_date': vehicle.leasing_start_date,
            'lease_end_date': vehicle.leasing_end_date,
            'lease_cycle_number': 1,
            'total_service_count': 0,
            'total_service_cost': 0.0,
            'routes_assigned': 0  # Track number of routes for workload balancing
        }
    
    return states


def validate_route(route) -> bool:
    """Validate route data."""
    if route.start_location_id is None:
        return False
    if route.end_location_id is None:
        return False
    if route.distance_km <= 0:
        return False
    if route.end_datetime <= route.start_datetime:
        return False
    return True


def update_relocation_window(vehicle_state: Dict, current_date: datetime, config) -> None:
    """
    Remove old relocations outside the swap policy window.
    Maintains rolling window for efficient swap policy checks.
    """
    cutoff = current_date - timedelta(days=config.swap_period_days)
    vehicle_state['relocations'] = [
        r for r in vehicle_state['relocations'] if r[0] >= cutoff
    ]


def check_and_reset_annual_km(vehicle_state: Dict, current_date: datetime) -> bool:
    """
    Check if lease year has rolled over and reset annual km counter.
    Handles multiple year rollovers if vehicle has been idle for > 1 year.
    Returns True if reset occurred.
    """
    reset_occurred = False
    
    # Handle multiple year boundaries if necessary
    while current_date >= vehicle_state['lease_end_date']:
        vehicle_state['km_driven_this_lease_year'] = 0
        vehicle_state['lease_cycle_number'] += 1
        vehicle_state['lease_start_date'] = vehicle_state['lease_end_date']
        vehicle_state['lease_end_date'] += timedelta(days=365)
        reset_occurred = True
    
    return reset_occurred


def pro_rate_km_across_lease_years(
    vehicle_state: Dict,
    route_start: datetime,
    route_end: datetime,
    route_km: int
) -> Tuple[int, int]:
    """
    If a route spans a lease year boundary, pro-rate the kilometers.
    
    Args:
        vehicle_state: Current vehicle state
        route_start: Route start datetime
        route_end: Route end datetime  
        route_km: Total route distance in km
    
    Returns:
        (km_in_current_year, km_in_next_year) tuple
    """
    lease_end = vehicle_state['lease_end_date']
    
    # Route doesn't span boundary
    if route_end <= lease_end:
        return route_km, 0
    
    if route_start >= lease_end:
        return 0, route_km
    
    # Route spans boundary - pro-rate by time
    total_duration = (route_end - route_start).total_seconds()
    if total_duration <= 0:
        return route_km, 0  # Shouldn't happen, but be safe
    
    duration_in_current_year = (lease_end - route_start).total_seconds()
    ratio_in_current_year = duration_in_current_year / total_duration
    
    km_in_current_year = int(route_km * ratio_in_current_year)
    km_in_next_year = route_km - km_in_current_year
    
    return km_in_current_year, km_in_next_year


def needs_service(vehicle_state: Dict, route, config) -> bool:
    """
    Check if vehicle needs service before/after route.
    Per clarifications: services have ±1000 km flexibility, NOT a hard block.
    Only returns True if ALREADY exceeded (not if WILL exceed).
    """
    # Only flag if ALREADY over the limit (needs immediate service)
    current_km = vehicle_state['km_since_last_service']
    max_allowed = vehicle_state['service_interval_km'] + config.service_tolerance_km
    return current_km > max_allowed


def calculate_service_time(vehicle_state: Dict, route, config) -> Tuple[datetime, datetime]:
    """
    Calculate when service would start and end if needed.
    Service happens BEFORE the route, as soon as vehicle is available.
    
    Returns:
        (service_start, service_end) tuple, or (None, None) if no service needed
    """
    if not needs_service(vehicle_state, route, config):
        return None, None
    
    # Service starts as soon as vehicle is available
    service_start = vehicle_state['available_from']
    service_end = service_start + timedelta(hours=config.service_duration_hours)
    
    return service_start, service_end


def schedule_service(vehicle_state: Dict, route, config) -> float:
    """
    Schedule and perform service if needed.
    Returns service cost (0 if no service needed).
    Updates vehicle state with service downtime.
    
    IMPORTANT: This function MUST use same timing logic as calculate_service_time()
    """
    service_start, service_end = calculate_service_time(vehicle_state, route, config)
    
    if service_start is None:
        return 0.0
    
    # Perform service
    vehicle_state['km_since_last_service'] = 0
    vehicle_state['total_service_count'] += 1
    vehicle_state['total_service_cost'] += config.service_cost_pln
    
    # Update availability to after service
    vehicle_state['available_from'] = service_end
    
    return config.service_cost_pln


def check_feasibility(
    vehicle_state: Dict,
    route,
    relation_lookup: Dict,
    config,
    relation_cache: Dict
) -> Tuple[bool, str]:
    """
    Check if vehicle can perform route.
    
    Checks:
    1. Route validation
    2. Time feasibility (available and can reach in time, INCLUDING service)
    3. Contract limits (won't exceed lifetime limit)
    4. Swap policy (hasn't relocated too recently)
    """
    # Validate route
    if not validate_route(route):
        return False, "Invalid route data"
    
    # Calculate availability AFTER service (if needed)
    # Use same logic as schedule_service() for consistency
    service_start, service_end = calculate_service_time(vehicle_state, route, config)
    
    if service_end is not None:
        # Service needed - vehicle available after service
        availability = service_end
    else:
        # No service needed - vehicle available immediately
        availability = vehicle_state['available_from']
    
    # Time check: can vehicle be available by route start?
    if availability > route.start_datetime:
        return False, "Not available yet (including potential service time)"
    
    # If relocation needed, check travel time and swap policy
    if vehicle_state['current_location_id'] != route.start_location_id:
        # Get relation using helper
        relation = get_cached_relation(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            config,
            relation_cache
        )
        
        if not relation:
            return False, "No path to start location"
        
        # Check if can reach in time (after service, if needed)
        arrival = availability + timedelta(minutes=relation.time)
        if arrival > route.start_datetime:
            return False, "Cannot reach in time (after service)"
        
        # Check swap policy (must have fresh relocation window)
        if len(vehicle_state['relocations']) >= config.max_swaps_per_period:
            return False, "Swap limit exceeded"
    
    # Contract limit check (HARD constraint)
    if vehicle_state['total_contract_limit_km']:
        # Include both route distance and potential relocation distance
        future_km = vehicle_state['total_lifetime_km'] + int(route.distance_km)
        
        # Add relocation distance if needed
        if vehicle_state['current_location_id'] != route.start_location_id:
            relation = get_cached_relation(
                vehicle_state['current_location_id'],
                route.start_location_id,
                relation_lookup,
                config,
                relation_cache
            )
            if relation:
                future_km += int(relation.dist)
        
        if future_km > vehicle_state['total_contract_limit_km']:
            return False, "Would exceed contract lifetime limit"
    
    return True, "OK"


def calculate_assignment_cost(
    vehicle_state: Dict,
    route,
    relation_lookup: Dict,
    config,
    relation_cache: Dict,
    vehicle_workloads: Dict = None
) -> float:
    """
    Calculate cost of assigning vehicle to route.
    
    Cost = Relocation cost + Overage cost + Service cost + Workload balancing penalty
    
    Args:
        vehicle_state: Current state of the vehicle
        route: Route to assign
        relation_lookup: Location relations
        config: Configuration
        relation_cache: Relation cache
        vehicle_workloads: Optional dict mapping vehicle_id -> route_count for workload balancing
    """
    cost = 0.0
    
    # Relocation cost (using helper)
    if vehicle_state['current_location_id'] != route.start_location_id:
        relation, relocation_cost = get_relocation_info(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            config,
            relation_cache
        )
        
        if relation is None:
            return INFEASIBLE_COST  # No path exists
        
        cost += relocation_cost
    
    # Overage cost (only for annual limit, not lifetime)
    future_km = vehicle_state['km_driven_this_lease_year'] + int(route.distance_km)
    if future_km > vehicle_state['annual_limit_km']:
        overage = future_km - vehicle_state['annual_limit_km']
        cost += overage * config.overage_per_km_pln
    
    # Service cost (actual service, not penalty)
    if needs_service(vehicle_state, route, config):
        cost += config.service_cost_pln
    
    # Workload balancing penalty
    # Penalize vehicles that already have many routes to encourage even distribution
    if vehicle_workloads:
        vehicle_id = vehicle_state['vehicle_id']
        current_workload = vehicle_workloads.get(vehicle_id, 0)
        
        if current_workload > 0:
            # Calculate average workload
            total_assigned = sum(vehicle_workloads.values())
            num_active_vehicles = sum(1 for w in vehicle_workloads.values() if w > 0)
            avg_workload = total_assigned / num_active_vehicles if num_active_vehicles > 0 else 0
            
            # Apply penalty if vehicle is significantly above average
            if current_workload > avg_workload * 1.2:  # More than 20% above average
                # Penalty scales with how far above average
                excess_ratio = (current_workload - avg_workload) / (avg_workload + 1)
                # Penalty: 50-500 PLN depending on excess
                workload_penalty = min(500, 50 + excess_ratio * 200)
                cost += workload_penalty
    
    return cost


def update_state(
    vehicle_state: Dict,
    route,
    relation_lookup: Dict,
    config,
    relation_cache: Dict
) -> None:
    """Update vehicle state after assignment."""
    # Check and reset annual km if lease year rolled over BEFORE route
    check_and_reset_annual_km(vehicle_state, route.start_datetime)
    
    # Clean relocation window
    update_relocation_window(vehicle_state, route.start_datetime, config)
    
    # Handle service if needed (before route)
    service_cost = schedule_service(vehicle_state, route, config)
    
    # Record relocation if occurred (using helper)
    if vehicle_state['current_location_id'] != route.start_location_id:
        relation = get_cached_relation(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            config,
            relation_cache
        )
        
        if relation:
            # Record relocation
            vehicle_state['relocations'].append((
                route.start_datetime,
                vehicle_state['current_location_id'],
                route.start_location_id
            ))
            
            # Add relocation distance to odometer
            reloc_km = int(relation.dist)
            vehicle_state['current_odometer_km'] += reloc_km
            vehicle_state['km_driven_this_lease_year'] += reloc_km
            vehicle_state['total_lifetime_km'] += reloc_km
            vehicle_state['km_since_last_service'] += reloc_km
    
    # Update location
    vehicle_state['current_location_id'] = route.end_location_id
    
    # Update mileage for route
    # Handle potential lease year boundary crossing during route
    distance_km = int(route.distance_km)
    km_current_year, km_next_year = pro_rate_km_across_lease_years(
        vehicle_state,
        route.start_datetime,
        route.end_datetime,
        distance_km
    )
    
    # Update odometer and lifetime km (always full distance)
    vehicle_state['current_odometer_km'] += distance_km
    vehicle_state['total_lifetime_km'] += distance_km
    vehicle_state['km_since_last_service'] += distance_km
    
    # Update annual km (might be split across years)
    vehicle_state['km_driven_this_lease_year'] += km_current_year
    
    # If route crossed boundary, reset and add next year km
    if km_next_year > 0:
        check_and_reset_annual_km(vehicle_state, route.end_datetime)
        vehicle_state['km_driven_this_lease_year'] += km_next_year
    
    # Update availability
    vehicle_state['available_from'] = route.end_datetime
    vehicle_state['last_route_id'] = route.id
    
    # Track workload
    vehicle_state['routes_assigned'] += 1


def build_future_chain(
    vehicle_state: Dict,
    route,
    all_routes: List,
    route_index: int,
    relation_lookup: Dict,
    config,
    relation_cache: Dict
) -> Tuple[float, List]:
    """
    Build chain of future routes this vehicle could complete after current route.
    Evaluates if assigning this vehicle sets up good future assignments.
    
    NOTE: This is OPTIONAL and disabled by default per spec recommendations.
    Only use if config.use_chain_optimization is True.
    
    Returns:
        (chain_score, future_routes)
    """
    if not config.use_chain_optimization:
        return 0.0, []
    
    if config.chain_depth <= 0 or route_index >= len(all_routes) - 1:
        return 0.0, []
    
    chain_score = 0.0
    chain_routes = []
    
    # Simulate vehicle state after completing current route
    future_state = deepcopy(vehicle_state)
    future_state['current_location_id'] = route.end_location_id
    future_state['available_from'] = route.end_datetime
    future_state['current_odometer_km'] += int(route.distance_km)
    future_state['km_driven_this_lease_year'] += int(route.distance_km)
    future_state['total_lifetime_km'] += int(route.distance_km)
    future_state['km_since_last_service'] += int(route.distance_km)
    
    # Look at next N routes within time window
    look_ahead_end = route.end_datetime + timedelta(days=config.look_ahead_days)
    candidate_routes = []
    
    max_scan = min(route_index + config.max_lookahead_routes, len(all_routes))
    
    for i in range(route_index + 1, max_scan):
        next_route = all_routes[i]
        
        if next_route.start_datetime > look_ahead_end:
            break
        
        # Check if feasible (relaxed - no swap policy check for future)
        if future_state['available_from'] > next_route.start_datetime:
            continue
        
        # Check if can reach
        if future_state['current_location_id'] != next_route.start_location_id:
            from data_loader import get_relation
            
            cache_key = (future_state['current_location_id'], next_route.start_location_id)
            if config.use_relation_cache and cache_key in relation_cache:
                relation = relation_cache[cache_key]
            else:
                relation = get_relation(
                    future_state['current_location_id'],
                    next_route.start_location_id,
                    relation_lookup,
                    use_pathfinding=config.use_pathfinding
                )
                if config.use_relation_cache:
                    relation_cache[cache_key] = relation
            
            if not relation:
                continue
            
            arrival = future_state['available_from'] + timedelta(minutes=relation.time)
            if arrival > next_route.start_datetime:
                continue
        
        # Calculate cost
        cost = calculate_assignment_cost(future_state, next_route, relation_lookup, config, relation_cache)
        
        if cost < INFEASIBLE_COST:
            # Score: lower cost = better opportunity
            route_score = 1000.0 / (cost + 100.0)
            candidate_routes.append((route_score, next_route, cost))
    
    # Take best future routes
    candidate_routes.sort(key=lambda x: x[0], reverse=True)
    
    for i, (score, future_route, cost) in enumerate(candidate_routes[:config.chain_depth]):
        # Diminishing weight for routes further ahead
        weight = 0.5 ** i
        chain_score += score * weight
        chain_routes.append(future_route)
    
    return chain_score, chain_routes


def filter_routes_by_lookahead(routes: List, lookahead_days: int) -> List:
    """
    Filter routes to only include those within lookahead window.
    Similar to placement lookahead strategy.
    
    Args:
        routes: All routes
        lookahead_days: Number of days to include (0 = all routes)
    
    Returns:
        Filtered list of routes
    """
    if lookahead_days <= 0 or not routes:
        return routes
    
    start_date = routes[0].start_datetime
    end_date = start_date + timedelta(days=lookahead_days)
    
    filtered = [r for r in routes if r.start_datetime < end_date]
    
    return filtered


def optimize_assignment_greedy(
    vehicles: List,
    routes: List,
    relation_lookup: Dict,
    config
) -> Tuple[List[Dict], Dict]:
    """
    Simple greedy assignment algorithm with workload balancing (recommended).
    For each route, assign cheapest available vehicle, with penalty for overworked vehicles.
    
    Only assigns routes within assignment_lookahead_days window.
    Keeps all routes for context.
    
    Returns:
        (assignments_list, final_states)
    """
    # Filter routes to only assign those within lookahead window
    all_routes_count = len(routes)
    routes_to_assign = routes
    
    if config.assignment_lookahead_days > 0:
        routes_to_assign = filter_routes_by_lookahead(routes, config.assignment_lookahead_days)
        print(f"[Assignment] Will assign {len(routes_to_assign)}/{all_routes_count} routes within {config.assignment_lookahead_days} day window")
    
    # Initialize
    start_date = routes[0].start_datetime if routes else datetime.now()
    vehicle_states = initialize_states(vehicles, start_date)
    relation_cache = {} if config.use_relation_cache else None
    
    # Track workloads for balancing
    vehicle_workloads = defaultdict(int)
    
    assignments = []
    unassigned = []
    
    console.print(f"\n[dim]Processing {len(routes_to_assign)} routes with {len(vehicles)} vehicles[/dim]")
    console.print(f"[dim]Strategy: Simple Greedy with Workload Balancing[/dim]")
    console.print(f"[dim]Relation caching: {config.use_relation_cache}[/dim]")
    
    # Process routes sequentially
    for route_index, route in enumerate(routes_to_assign):
        # Progress reporting
        if route_index > 0 and route_index % config.progress_report_interval == 0:
            progress_pct = (route_index / len(routes_to_assign)) * 100
            active_vehicles = sum(1 for w in vehicle_workloads.values() if w > 0)
            avg_workload = sum(vehicle_workloads.values()) / active_vehicles if active_vehicles > 0 else 0
            console.print(f"[cyan]Progress:[/cyan] {route_index}/{len(routes_to_assign)} ({progress_pct:.1f}%) - "
                  f"Assigned: [green]{len(assignments)}[/green], Unassigned: [yellow]{len(unassigned)}[/yellow], "
                  f"Active vehicles: {active_vehicles}, Avg workload: {avg_workload:.1f}")
        
        # Find best vehicle (minimum cost with workload balancing)
        best_vehicle_id = None
        best_cost = INFEASIBLE_COST
        
        for vehicle_id, state in vehicle_states.items():
            # Check feasibility
            feasible, reason = check_feasibility(state, route, relation_lookup, config, relation_cache)
            
            if not feasible:
                continue
            
            # Calculate cost with workload balancing
            cost = calculate_assignment_cost(state, route, relation_lookup, config, relation_cache, vehicle_workloads)
            
            if cost < best_cost:
                best_cost = cost
                best_vehicle_id = vehicle_id
        
        # Assign or mark unassigned
        if best_vehicle_id is not None:
            # Create assignment record
            assignment = {
                'route_id': route.id,
                'vehicle_id': best_vehicle_id,
                'date': route.start_datetime,
                'route_start_location': route.start_location_id,
                'route_end_location': route.end_location_id,
                'requires_relocation': vehicle_states[best_vehicle_id]['current_location_id'] != route.start_location_id,
                'cost': best_cost,
                'chain_score': 0.0
            }
            assignments.append(assignment)
            
            # Update workload tracking
            vehicle_workloads[best_vehicle_id] += 1
            
            # Update state
            update_state(vehicle_states[best_vehicle_id], route, relation_lookup, config, relation_cache)
        else:
            unassigned.append(route.id)
            if len(unassigned) <= 10:  # Only print first 10 to avoid spam
                console.print(f"[yellow]WARNING: No feasible vehicle for route {route.id}[/yellow]")
    
    # Print final workload distribution
    active_vehicles = sum(1 for w in vehicle_workloads.values() if w > 0)
    if active_vehicles > 0:
        avg_workload = sum(vehicle_workloads.values()) / active_vehicles
        max_workload = max(vehicle_workloads.values())
        min_workload = min(w for w in vehicle_workloads.values() if w > 0) if active_vehicles > 0 else 0
        console.print(f"\n[cyan]Workload distribution:[/cyan] {active_vehicles}/{len(vehicles)} vehicles used")
        console.print(f"   Average: {avg_workload:.1f} routes/vehicle")
        console.print(f"   Range: {min_workload} - {max_workload} routes")
    
    console.print(f"\n[green]✓[/green] Complete: {len(assignments)}/{len(routes_to_assign)} assigned ([yellow]{len(unassigned)}[/yellow] unassigned)")
    
    return assignments, vehicle_states


def optimize_assignment_with_lookahead(
    vehicles: List,
    routes: List,
    relation_lookup: Dict,
    config
) -> Tuple[List[Dict], Dict]:
    """
    Greedy assignment with optional look-ahead and chaining.
    OPTIMIZED FOR 100% FULFILLMENT: Pre-sorts routes to maximize chaining opportunities.
    
    For each route:
    1. Find feasible vehicles
    2. Calculate immediate cost
    3. Build future route chains (look-ahead) if enabled
    4. Combine immediate cost with future opportunity score
    5. Assign vehicle with best combined score
    
    Only assigns routes within assignment_lookahead_days window.
    Keeps all routes for chain building context.
    
    Returns:
        (assignments_list, final_states)
    """
    # Filter routes to only assign those within lookahead window
    all_routes_count = len(routes)
    routes_to_assign = routes
    
    if config.assignment_lookahead_days > 0:
        routes_to_assign = filter_routes_by_lookahead(routes, config.assignment_lookahead_days)
        console.print(f"[dim]Will assign {len(routes_to_assign)}/{all_routes_count} routes within {config.assignment_lookahead_days} day window[/dim]")
    
    # OPTIMIZATION: Group routes by location clusters to improve chaining
    # Sort by (start_time, start_location) to process location-based batches
    console.print(f"[dim]Sorting routes to maximize chaining opportunities...[/dim]")
    routes_to_assign_sorted = sorted(routes_to_assign, key=lambda r: (r.start_datetime, r.start_location_id))
    routes_to_assign = routes_to_assign_sorted
    
    # Initialize
    start_date = routes[0].start_datetime if routes else datetime.now()
    vehicle_states = initialize_states(vehicles, start_date)
    relation_cache = {} if config.use_relation_cache else None
    
    assignments = []
    unassigned = []
    
    console.print(f"\n[dim]Processing {len(routes_to_assign)} routes with {len(vehicles)} vehicles[/dim]")
    console.print(f"[dim]Strategy: Greedy with Look-Ahead[/dim]")
    console.print(f"[dim]Chain lookahead: {config.look_ahead_days} days, Chain depth: {config.chain_depth}[/dim]")
    console.print(f"[dim]Chain optimization: {config.use_chain_optimization}[/dim]")
    
    # Process routes sequentially (only assign routes_to_assign)
    for assign_index, route in enumerate(routes_to_assign):
        # Progress reporting
        if assign_index > 0 and assign_index % config.progress_report_interval == 0:
            progress_pct = (assign_index / len(routes_to_assign)) * 100
            console.print(f"[cyan]Progress:[/cyan] {assign_index}/{len(routes_to_assign)} ({progress_pct:.1f}%)")
        
        # Find the index of this route in the full routes list (for chain building)
        full_route_index = routes.index(route) if route in routes else assign_index
        
        # Find best vehicle with look-ahead
        # PRIORITY #1: Find ANY feasible vehicle (100% fulfillment goal)
        # PRIORITY #2: Among feasible vehicles, pick best cost + chain score
        best_vehicle_id = None
        best_score = INFEASIBLE_COST  # Lower is better
        best_immediate_cost = INFEASIBLE_COST
        best_chain_score = 0.0
        
        # NEW: Track if we found ANY feasible vehicle
        feasible_candidates = []
        
        for vehicle_id, state in vehicle_states.items():
            # Check feasibility
            feasible, reason = check_feasibility(state, route, relation_lookup, config, relation_cache)
            
            if not feasible:
                continue
            
            # Calculate immediate cost
            immediate_cost = calculate_assignment_cost(state, route, relation_lookup, config, relation_cache)
            
            # Build future chain (look-ahead) using full routes list for context
            if config.use_chain_optimization and config.look_ahead_days > 0 and config.chain_depth > 0:
                chain_score, chain_routes = build_future_chain(
                    state, route, routes, full_route_index,
                    relation_lookup, config, relation_cache
                )
            else:
                chain_score = 0.0
            
            # Feasible candidate found!
            feasible_candidates.append((vehicle_id, immediate_cost, chain_score))
            
            # Combined score: HEAVILY weight chain score to maximize fulfillment
            # The better the chain, the more routes we can fulfill without relocations
            # Use higher weight for chain score to prioritize long-term feasibility
            effective_cost = immediate_cost - (chain_score * config.chain_weight * 2.0)
            
            if effective_cost < best_score:
                best_score = effective_cost
                best_vehicle_id = vehicle_id
                best_immediate_cost = immediate_cost
                best_chain_score = chain_score
        
        # If we have feasible candidates but best_score is still inf, take the first one
        # This ensures we ALWAYS assign if ANY vehicle can do it (100% fulfillment priority)
        if feasible_candidates and best_vehicle_id is None:
            best_vehicle_id, best_immediate_cost, best_chain_score = feasible_candidates[0]
        
        # Assign or mark unassigned
        if best_vehicle_id is not None:
            # Create assignment record
            assignment = {
                'route_id': route.id,
                'vehicle_id': best_vehicle_id,
                'date': route.start_datetime,
                'route_start_location': route.start_location_id,
                'route_end_location': route.end_location_id,
                'requires_relocation': vehicle_states[best_vehicle_id]['current_location_id'] != route.start_location_id,
                'cost': best_immediate_cost,
                'chain_score': best_chain_score
            }
            assignments.append(assignment)
            
            # Update state
            update_state(vehicle_states[best_vehicle_id], route, relation_lookup, config, relation_cache)
        else:
            unassigned.append(route.id)
            
            # Debug: sample rejection reasons for first few unassigned
            if len(unassigned) <= 20:
                reasons = {}
                for vehicle_id, state in vehicle_states.items():
                    feasible, reason = check_feasibility(state, route, relation_lookup, config, relation_cache)
                    if not feasible:
                        reasons[reason] = reasons.get(reason, 0) + 1
                console.print(f"[yellow]Route {route.id} unassigned - reasons: {dict(list(reasons.items())[:3])}[/yellow]")
    
    console.print(f"\n[green]✓[/green] Complete: {len(assignments)}/{len(routes_to_assign)} assigned ([yellow]{len(unassigned)}[/yellow] unassigned)")
    
    return assignments, vehicle_states


def optimize_assignment(
    vehicles: List,
    routes: List,
    relation_lookup: Dict,
    config
) -> Tuple[List[Dict], Dict]:
    """
    Main assignment optimization function.
    Routes to appropriate strategy based on config.
    
    Returns:
        (assignments_list, final_states)
    """
    if config.assignment_strategy == 'greedy_with_lookahead':
        return optimize_assignment_with_lookahead(vehicles, routes, relation_lookup, config)
    else:
        # Default: simple greedy (recommended)
        return optimize_assignment_greedy(vehicles, routes, relation_lookup, config)