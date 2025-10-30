"""
Core assignment algorithm - pure logic, no I/O.
Assigns vehicles to routes minimizing total cost while respecting constraints.
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta


def initialize_states(vehicles: List, start_date: datetime) -> Dict:
    """
    Initialize vehicle states for simulation.
    Available 24h before start to allow initial positioning.
    """
    states = {}
    available_from = start_date - timedelta(hours=24)
    
    for vehicle in vehicles:
        states[vehicle.id] = {
            'vehicle_id': vehicle.id,
            'current_location_id': vehicle.current_location_id,
            'current_odometer_km': vehicle.current_odometer_km,
            'km_since_last_service': 0,
            'km_driven_this_lease_year': 0,
            'total_lifetime_km': vehicle.current_odometer_km,
            'available_from': available_from,
            'last_route_id': None,
            'relocations': [],
            'annual_limit_km': vehicle.annual_limit_km,
            'service_interval_km': vehicle.service_interval_km,
            'total_contract_limit_km': vehicle.total_contract_limit_km
        }
    
    return states


def check_feasibility(vehicle_state: Dict, route, relation_lookup: Dict, config) -> Tuple[bool, str]:
    """
    Check if vehicle can perform route.
    
    Checks:
    1. Time feasibility (available and can reach in time)
    2. Contract limits (won't exceed lifetime limit)
    3. Swap policy (hasn't relocated too recently)
    """
    from data_loader import get_relation
    
    # Time check
    if vehicle_state['available_from'] > route.start_datetime:
        return False, "Not available yet"
    
    # If relocation needed, check travel time
    if vehicle_state['current_location_id'] != route.start_location_id:
        relation = get_relation(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            use_pathfinding=False  # Direct paths only
        )
        
        if not relation:
            return False, "No direct path"
        
        arrival = vehicle_state['available_from'] + timedelta(hours=relation.time)
        if arrival > route.start_datetime:
            return False, "Cannot reach in time"
        
        # Check swap policy
        recent_relocations = [r for r in vehicle_state['relocations']
                            if (route.start_datetime - r[0]).days < config.swap_period_days]
        if len(recent_relocations) >= config.max_swaps_per_period:
            return False, "Swap limit exceeded"
    
    # Contract limit check
    if vehicle_state['total_contract_limit_km']:
        future_km = vehicle_state['total_lifetime_km'] + int(route.distance_km)
        if future_km > vehicle_state['total_contract_limit_km']:
            return False, "Would exceed contract limit"
    
    return True, "OK"


def calculate_assignment_cost(vehicle_state: Dict, route, relation_lookup: Dict, config) -> float:
    """
    Calculate cost of assigning vehicle to route.
    
    Cost = Relocation cost + Overage cost + Service penalty
    """
    from data_loader import get_relation
    
    cost = 0.0
    
    # Relocation cost
    if vehicle_state['current_location_id'] != route.start_location_id:
        relation = get_relation(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            use_pathfinding=False
        )
        
        if relation:
            cost += config.relocation_base_cost_pln
            cost += relation.dist * config.relocation_per_km_pln
            cost += relation.time * config.relocation_per_hour_pln
        else:
            cost += 999999  # No path
    
    # Overage cost
    future_km = vehicle_state['km_driven_this_lease_year'] + int(route.distance_km)
    if future_km > vehicle_state['annual_limit_km']:
        overage = future_km - vehicle_state['annual_limit_km']
        cost += overage * config.overage_per_km_pln
    
    # Service penalty
    future_service_km = vehicle_state['km_since_last_service'] + int(route.distance_km)
    if future_service_km > vehicle_state['service_interval_km'] + config.service_tolerance_km:
        cost += config.service_penalty_pln
    
    return cost


def update_state(vehicle_state: Dict, route, relation_lookup: Dict, config) -> None:
    """Update vehicle state after assignment."""
    from data_loader import get_relation
    
    # Record relocation if occurred
    if vehicle_state['current_location_id'] != route.start_location_id:
        vehicle_state['relocations'].append((
            route.start_datetime,
            vehicle_state['current_location_id'],
            route.start_location_id
        ))
        
        # Add relocation distance
        relation = get_relation(
            vehicle_state['current_location_id'],
            route.start_location_id,
            relation_lookup,
            use_pathfinding=False
        )
        if relation:
            reloc_km = int(relation.dist)
            vehicle_state['current_odometer_km'] += reloc_km
            vehicle_state['km_driven_this_lease_year'] += reloc_km
            vehicle_state['total_lifetime_km'] += reloc_km
            vehicle_state['km_since_last_service'] += reloc_km
    
    # Update location
    vehicle_state['current_location_id'] = route.end_location_id
    
    # Update mileage
    distance = int(route.distance_km)
    vehicle_state['current_odometer_km'] += distance
    vehicle_state['km_driven_this_lease_year'] += distance
    vehicle_state['total_lifetime_km'] += distance
    vehicle_state['km_since_last_service'] += distance
    
    # Update availability
    vehicle_state['available_from'] = route.end_datetime
    vehicle_state['last_route_id'] = route.id


def optimize_assignment(
    vehicles: List,
    routes: List,
    relation_lookup: Dict,
    config
) -> Tuple[List[Dict], Dict]:
    """
    Main assignment optimization function.
    Greedy algorithm: for each route, assign cheapest feasible vehicle.
    
    Returns:
        (assignments_list, final_states)
    """
    # Initialize
    start_date = routes[0].start_datetime if routes else datetime.now()
    vehicle_states = initialize_states(vehicles, start_date)
    
    assignments = []
    unassigned = []
    
    # Process routes sequentially
    for route in routes:
        # Find best vehicle
        best_vehicle_id = None
        best_cost = float('inf')
        
        for vehicle_id, state in vehicle_states.items():
            # Check feasibility
            feasible, reason = check_feasibility(state, route, relation_lookup, config)
            
            if not feasible:
                continue
            
            # Calculate cost
            cost = calculate_assignment_cost(state, route, relation_lookup, config)
            
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
                'cost': best_cost
            }
            assignments.append(assignment)
            
            # Update state
            update_state(vehicle_states[best_vehicle_id], route, relation_lookup, config)
        else:
            unassigned.append(route.id)
    
    return assignments, vehicle_states

