#!/usr/bin/env python3
"""
Test runner for assignment algorithm with look-ahead and chaining.
"""
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import load_all_data
from models import AssignmentConfig
from algorithms.placement import optimize_placement
from algorithms.assignment import optimize_assignment


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
    placement, quality = optimize_placement(
        vehicles, routes, relation_lookup, config, strategy=config.placement_strategy
    )
    # Apply placement
    for vehicle in vehicles:
        if vehicle.id in placement:
            vehicle.current_location_id = placement[vehicle.id]
    print(f"   ✓ Completed in {time.time()-start:.2f}s")
    print(f"   • {quality['locations_used']} locations used")
    
    # Run assignment
    print(f"\n[4/5] Running assignment algorithm...")
    if config.use_chain_optimization:
        print(f"   Strategy: {config.assignment_strategy} with look-ahead ({config.look_ahead_days}d) + chaining (depth {config.chain_depth})")
    else:
        print(f"   Strategy: {config.assignment_strategy} (simple greedy, spec-compliant)")
    start = time.time()
    assignments, final_states = optimize_assignment(
        vehicles, routes, relation_lookup, config
    )
    elapsed = time.time() - start
    print(f"   ✓ Completed in {elapsed:.2f}s")
    if assignments:
        print(f"   • Speed: {len(assignments)/elapsed:.1f} routes/second")
    
    # Calculate statistics
    print(f"\n[5/5] Results:")
    print(f"   Routes assigned: {len(assignments)}/{len(routes)} ({len(assignments)/len(routes)*100:.1f}%)")
    print(f"   Routes unassigned: {len(routes) - len(assignments)}")
    
    # Relocation stats
    relocations = sum(1 for a in assignments if a['requires_relocation'])
    print(f"\n   Relocations: {relocations} ({relocations/len(assignments)*100:.1f}%)")
    
    # Chain score stats
    chain_scores = [a.get('chain_score', 0) for a in assignments]
    avg_chain_score = sum(chain_scores) / len(chain_scores) if chain_scores else 0
    print(f"   Avg chain score: {avg_chain_score:.3f}")
    
    # Vehicle utilization
    routes_per_vehicle = {}
    for a in assignments:
        vid = a['vehicle_id']
        routes_per_vehicle[vid] = routes_per_vehicle.get(vid, 0) + 1
    
    utilized = len(routes_per_vehicle)
    avg_routes = sum(routes_per_vehicle.values()) / len(routes_per_vehicle) if routes_per_vehicle else 0
    print(f"\n   Vehicles used: {utilized}/{len(vehicles)} ({utilized/len(vehicles)*100:.1f}%)")
    print(f"   Avg routes per vehicle: {avg_routes:.1f}")
    
    # Cost estimates
    total_cost = sum(a.get('cost', 0) for a in assignments)
    avg_cost = total_cost / len(assignments) if assignments else 0
    print(f"\n   Estimated total cost: {total_cost:,.0f} PLN")
    print(f"   Avg cost per route: {avg_cost:.2f} PLN")
    
    print("\n" + "="*70)
    print("✨ Test complete!")
    print("="*70 + "\n")
    
    return assignments, final_states


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test assignment algorithm')
    parser.add_argument('--config', default='algorithm_config.json', 
                       help='Path to config file')
    
    args = parser.parse_args()
    
    test_assignment(config_path=args.config)

