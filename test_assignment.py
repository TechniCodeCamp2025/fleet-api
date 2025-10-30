#!/usr/bin/env python3
"""
Test runner for assignment algorithm with look-ahead and chaining.
"""
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import load_all_data
from models import AssignmentConfig, PlacementResult, AssignmentResult
from placement import calculate_placement, apply_placement_to_vehicles
from assignment import assign_routes
from output import write_assignments_csv, write_vehicle_states_csv
import csv


def load_config_from_file(config_path='algorithm_config.json'):
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    
    max_vehicles_per_location = cfg['placement'].get('max_vehicles_per_location')
    
    return AssignmentConfig(
        # Costs
        relocation_base_cost_pln=cfg['costs']['relocation_base_cost_pln'],
        relocation_per_km_pln=cfg['costs']['relocation_per_km_pln'],
        relocation_per_hour_pln=cfg['costs']['relocation_per_hour_pln'],
        overage_per_km_pln=cfg['costs']['overage_per_km_pln'],
        service_cost_pln=cfg['service_policy'].get('service_cost_pln', 2000.0),
        
        # Service policy
        service_tolerance_km=cfg['service_policy']['service_tolerance_km'],
        service_duration_hours=cfg['service_policy']['service_duration_hours'],
        service_penalty_pln=cfg['service_policy']['service_penalty_pln'],
        
        # Swap policy
        max_swaps_per_period=cfg['swap_policy']['max_swaps_per_period'],
        swap_period_days=cfg['swap_policy']['swap_period_days'],
        
        # Assignment parameters
        assignment_lookahead_days=cfg['assignment'].get('assignment_lookahead_days', 0),
        look_ahead_days=cfg['assignment'].get('look_ahead_days', 0),
        chain_depth=cfg['assignment'].get('chain_depth', 0),
        chain_weight=cfg['assignment'].get('chain_weight', 10.0),
        max_lookahead_routes=cfg['assignment'].get('max_lookahead_routes', 50),
        use_chain_optimization=cfg['assignment'].get('use_chain_optimization', False),
        assignment_strategy=cfg['assignment'].get('strategy', 'greedy'),
        
        # Placement parameters
        placement_lookahead_days=cfg['placement']['lookahead_days'],
        placement_strategy=cfg['placement'].get('strategy', 'cost_matrix'),
        placement_max_concentration=cfg['placement'].get('max_concentration', 0.30),
        placement_max_vehicles_per_location=max_vehicles_per_location,
        
        # Performance
        use_pathfinding=cfg['performance'].get('use_pathfinding', False),
        use_relation_cache=cfg['performance'].get('use_relation_cache', True),
        progress_report_interval=cfg['performance'].get('progress_report_interval', 1000)
    )


def test_assignment(config_path='algorithm_config.json'):
    """Test full optimization: placement + assignment."""
    
    print("\n" + "="*70)
    print(" " * 15 + "ASSIGNMENT ALGORITHM TEST")
    print(" " * 10 + "Greedy with Look-Ahead & Chaining")
    print("="*70)
    
    # Load config
    print(f"\n[1/5] Loading configuration from {config_path}...")
    config = load_config_from_file(config_path)
    print(f"   ✓ Assignment strategy: {config.assignment_strategy}")
    print(f"   ✓ Assignment lookahead: {config.assignment_lookahead_days} days (routes to assign)")
    print(f"   ✓ Chain lookahead: {config.look_ahead_days} days")
    print(f"   ✓ Chain depth: {config.chain_depth}")
    print(f"   ✓ Chain optimization: {config.use_chain_optimization}")
    print(f"   ✓ Swap period: {config.swap_period_days} days")
    print(f"   ✓ Relation cache: {config.use_relation_cache}")
    
    # Load data
    print("\n[2/5] Loading data...")
    start = time.time()
    vehicles, locations, relation_lookup, routes = load_all_data('data')
    print(f"   ✓ Loaded in {time.time()-start:.2f}s")
    print(f"   • {len(vehicles)} vehicles")
    print(f"   • {len(locations)} locations")
    print(f"   • {len(routes)} total routes")
    
    # Routes filtered by lookahead inside algorithms
    if config.assignment_lookahead_days > 0:
        print(f"   • Assignment will process routes within {config.assignment_lookahead_days} day lookahead window")
    
    # Run placement
    print(f"\n[3/5] Running placement algorithm...")
    start = time.time()
    placement_result = calculate_placement(
        vehicles, routes, locations, relation_lookup, config
    )
    apply_placement_to_vehicles(vehicles, placement_result.placements)
    print(f"   ✓ Completed in {time.time()-start:.2f}s")
    print(f"   • {placement_result.locations_used} locations used")
    
    # Run assignment
    print(f"\n[4/5] Running assignment algorithm...")
    if config.use_chain_optimization:
        print(f"   Strategy: {config.assignment_strategy} with look-ahead ({config.look_ahead_days}d) + chaining (depth {config.chain_depth})")
    else:
        print(f"   Strategy: {config.assignment_strategy} (simple greedy, spec-compliant)")
    start = time.time()
    assignment_result = assign_routes(
        vehicles, routes, relation_lookup, config
    )
    elapsed = time.time() - start
    print(f"   ✓ Completed in {elapsed:.2f}s")
    if assignment_result.assignments:
        print(f"   • Speed: {len(assignment_result.assignments)/elapsed:.1f} routes/second")
    
    # Calculate statistics
    print(f"\n[5/5] Results:")
    print(f"   Routes assigned: {assignment_result.routes_assigned}/{len(routes)} ({assignment_result.routes_assigned/len(routes)*100:.1f}%)")
    print(f"   Routes unassigned: {assignment_result.routes_unassigned}")
    
    # Relocation stats
    relocations = sum(1 for a in assignment_result.assignments if a.requires_relocation)
    print(f"\n   Relocations: {relocations} ({relocations/len(assignment_result.assignments)*100:.1f}%)")
    
    # Chain score stats
    chain_scores = [a.chain_score for a in assignment_result.assignments]
    avg_chain_score = sum(chain_scores) / len(chain_scores) if chain_scores else 0
    print(f"   Avg chain score: {avg_chain_score:.3f}")
    
    # Vehicle utilization
    routes_per_vehicle = {}
    for a in assignment_result.assignments:
        vid = a.vehicle_id
        routes_per_vehicle[vid] = routes_per_vehicle.get(vid, 0) + 1
    
    utilized = len(routes_per_vehicle)
    avg_routes = sum(routes_per_vehicle.values()) / len(routes_per_vehicle) if routes_per_vehicle else 0
    print(f"\n   Vehicles used: {utilized}/{len(vehicles)} ({utilized/len(vehicles)*100:.1f}%)")
    print(f"   Avg routes per vehicle: {avg_routes:.1f}")
    
    # Cost estimates
    print(f"\n   Estimated total cost: {assignment_result.total_cost:,.0f} PLN")
    print(f"   Avg cost per route: {assignment_result.avg_cost_per_route:.2f} PLN")
    
    # Export CSV files
    print(f"\n[6/6] Exporting results to CSV...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    assignments_file = f"output/assignments_{timestamp}.csv"
    Path("output").mkdir(parents=True, exist_ok=True)
    write_assignments_csv(assignment_result.assignments, assignments_file)
    
    vehicle_states_file = f"output/vehicle_states_{timestamp}.csv"
    write_vehicle_states_csv(assignment_result.vehicle_states, vehicle_states_file)
    
    # Save processed vehicles data
    vehicles_processed_file = f"output/vehicles_processed_{timestamp}.csv"
    with open(vehicles_processed_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Id', 'registration_number', 'brand', 'service_interval_km', 
                        'Leasing_start_km', 'leasing_limit_km', 'leasing_start_date', 
                        'leasing_end_date', 'current_odometer_km', 'Current_location_id'])
        for vehicle in vehicles:
            writer.writerow([
                vehicle.id,
                vehicle.registration_number,
                vehicle.brand,
                vehicle.service_interval_km,
                vehicle.leasing_start_km,
                vehicle.leasing_limit_km,
                vehicle.leasing_start_date.strftime('%Y-%m-%d %H:%M:%S'),
                vehicle.leasing_end_date.strftime('%Y-%m-%d %H:%M:%S'),
                vehicle.current_odometer_km,
                vehicle.current_location_id if vehicle.current_location_id is not None else 'N/A'
            ])
    
    # Save processed routes data
    routes_processed_file = f"output/routes_processed_{timestamp}.csv"
    with open(routes_processed_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'start_datetime', 'end_datetime', 'distance_km'])
        for route in routes:
            writer.writerow([
                route.id,
                route.start_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                route.end_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                route.distance_km
            ])
    
    # Save processed locations data
    locations_processed_file = f"output/locations_processed_{timestamp}.csv"
    with open(locations_processed_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'lat', 'long', 'is_hub'])
        for location in locations:
            writer.writerow([
                location.id,
                location.name,
                location.lat,
                location.lon,
                1 if location.is_hub else 0
            ])
    
    # Save summary statistics to CSV
    summary_file = f"output/summary_{timestamp}.csv"
    with open(summary_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Routes', len(routes)])
        writer.writerow(['Routes Assigned', assignment_result.routes_assigned])
        writer.writerow(['Routes Unassigned', assignment_result.routes_unassigned])
        writer.writerow(['Assignment Rate (%)', f"{assignment_result.routes_assigned/len(routes)*100:.1f}"])
        writer.writerow(['Relocations', relocations])
        writer.writerow(['Relocation Rate (%)', f"{relocations/len(assignment_result.assignments)*100:.1f}" if assignment_result.assignments else "0.0"])
        writer.writerow(['Average Chain Score', f"{avg_chain_score:.3f}"])
        writer.writerow(['Total Vehicles', len(vehicles)])
        writer.writerow(['Vehicles Used', utilized])
        writer.writerow(['Vehicle Utilization (%)', f"{utilized/len(vehicles)*100:.1f}"])
        writer.writerow(['Average Routes per Vehicle', f"{avg_routes:.1f}"])
        writer.writerow(['Total Cost (PLN)', f"{assignment_result.total_cost:,.0f}"])
        writer.writerow(['Average Cost per Route (PLN)', f"{assignment_result.avg_cost_per_route:.2f}"])
        writer.writerow(['Locations Used', placement_result.locations_used])
        writer.writerow(['Processing Time (s)', f"{elapsed:.2f}"])
        writer.writerow(['Routes per Second', f"{len(assignment_result.assignments)/elapsed:.1f}" if assignment_result.assignments and elapsed > 0 else "0.0"])
    
    print(f"   ✓ CSV files exported successfully")
    print(f"   • {assignments_file}")
    print(f"   • {vehicle_states_file}")
    print(f"   • {vehicles_processed_file}")
    print(f"   • {routes_processed_file}")
    print(f"   • {locations_processed_file}")
    print(f"   • {summary_file}")
    
    print("\n" + "="*70)
    print("✨ Test complete!")
    print("="*70 + "\n")
    
    return assignment_result.assignments, assignment_result.vehicle_states


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test assignment algorithm')
    parser.add_argument('--config', default='algorithm_config.json', 
                       help='Path to config file')
    
    args = parser.parse_args()
    
    test_assignment(config_path=args.config)

