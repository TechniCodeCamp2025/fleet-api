#!/usr/bin/env python3
"""
Simple test runner for placement algorithm.
Separated from algorithm logic for clarity.
"""
import sys
import json
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import load_all_data
from models import AssignmentConfig
from algorithms.placement import optimize_placement


def print_separator(title=""):
    print("\n" + "="*60)
    if title:
        print(f"  {title}")
        print("="*60)


def load_config(config_path='algorithm_config.json'):
    """Load configuration from JSON file"""
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    
    return AssignmentConfig(
        # Costs
        relocation_base_cost_pln=cfg['costs']['relocation_base_cost_pln'],
        relocation_per_km_pln=cfg['costs']['relocation_per_km_pln'],
        relocation_per_hour_pln=cfg['costs']['relocation_per_hour_pln'],
        overage_per_km_pln=cfg['costs']['overage_per_km_pln'],
        
        # Service
        service_tolerance_km=cfg['service_policy']['service_tolerance_km'],
        service_duration_hours=cfg['service_policy']['service_duration_hours'],
        service_penalty_pln=cfg['service_policy']['service_penalty_pln'],
        
        # Swap policy
        max_swaps_per_period=cfg['swap_policy']['max_swaps_per_period'],
        swap_period_days=cfg['swap_policy']['swap_period_days'],
        
        # Placement
        placement_lookahead_days=cfg['placement']['lookahead_days'],
        placement_strategy=cfg['placement'].get('strategy', 'cost_matrix'),
        placement_max_concentration=cfg['placement'].get('max_concentration', 0.30),
        placement_max_vehicles_per_location=cfg['placement'].get('max_vehicles_per_location'),
        
        # Assignment
        look_ahead_days=cfg['assignment']['look_ahead_days'],
        chain_depth=cfg['assignment']['chain_depth'],
        
        # Performance
        use_pathfinding=cfg['performance'].get('use_pathfinding', False)
    )


def test_placement(config_path='algorithm_config.json'):
    """Test placement algorithm using config file."""
    
    print_separator("PLACEMENT ALGORITHM TEST")
    
    # Load config
    print("\n[1/5] Loading configuration...")
    config = load_config(config_path)
    print(f"   ✓ Strategy: {config.placement_strategy}")
    print(f"   ✓ Lookahead days: {config.placement_lookahead_days}")
    print(f"   ✓ Max concentration: {config.placement_max_concentration:.0%}")
    
    # Load data
    print("\n[2/5] Loading data...")
    start = time.time()
    vehicles, locations, relation_lookup, routes = load_all_data('data')
    print(f"   ✓ Loaded in {time.time()-start:.2f}s")
    print(f"   • {len(vehicles)} vehicles")
    print(f"   • {len(locations)} locations")
    print(f"   • {len(routes)} total routes")
    
    # Filter to lookahead window
    if routes:
        from datetime import timedelta
        start_date = routes[0].start_datetime
        end_date = start_date + timedelta(days=config.placement_lookahead_days)
        lookahead_routes = [r for r in routes if r.start_datetime < end_date]
        print(f"   • {len(lookahead_routes)} routes in first {config.placement_lookahead_days} days (lookahead window)")
    
    # Run placement
    print(f"\n[3/5] Running placement algorithm...")
    start = time.time()
    placement, quality = optimize_placement(
        vehicles, routes, relation_lookup, config, strategy=config.placement_strategy
    )
    elapsed = time.time() - start
    print(f"   ✓ Completed in {elapsed:.2f}s")
    
    # Show results
    print(f"\n[4/5] Placement Results:")
    print(f"   • Vehicles placed: {quality['total_vehicles']}")
    print(f"   • Locations used: {quality['locations_used']}")
    print(f"   • Max concentration: {quality['max_concentration']:.1%}")
    print(f"   • Demand coverage: {quality['demand_coverage']:.1%}")
    print(f"   • Demand satisfaction: {quality.get('demand_satisfaction', 0):.1%}")
    print(f"   • Estimated relocation cost: {quality['estimated_relocation_cost']:,.0f} PLN")
    
    # Show distribution
    print(f"\n[5/5] Vehicle Distribution (Top 10 locations):")
    from collections import Counter
    dist = Counter(placement.values())
    for i, (loc_id, count) in enumerate(dist.most_common(10), 1):
        pct = count / len(vehicles) * 100
        print(f"   {i:2d}. Location {loc_id:3d}: {count:3d} vehicles ({pct:5.1f}%)")
    
    print_separator()
    
    # Quality assessment
    print("\n📊 Quality Assessment:")
    if quality['max_concentration'] > 0.5:
        print("   ⚠️  High concentration - too many vehicles at one location")
    elif quality['max_concentration'] < 0.05:
        print("   ⚠️  Too scattered - vehicles spread too thin")
    else:
        print("   ✅ Good clustering balance")
    
    if quality['demand_coverage'] >= 0.95:
        print("   ✅ Excellent coverage - vehicles at high-demand locations")
    elif quality['demand_coverage'] >= 0.80:
        print("   ✅ Good coverage")
    else:
        print("   ⚠️  Poor coverage - vehicles not at demand locations")
    
    if quality.get('demand_satisfaction', 0) >= 0.70:
        print("   ✅ Excellent demand matching")
    elif quality.get('demand_satisfaction', 0) >= 0.40:
        print("   ✅ Good demand matching")
    else:
        print("   ⚠️  Poor demand matching - distribution doesn't match demand pattern")
    
    if quality['estimated_relocation_cost'] < 15_000_000:
        print("   ✅ Excellent cost estimate (< 15M PLN)")
    elif quality['estimated_relocation_cost'] < 30_000_000:
        print("   ✅ Good cost estimate (< 30M PLN)")
    else:
        print("   ⚠️  High estimated costs - may need better distribution")
    
    print("\n✨ Test complete!\n")
    
    return placement, quality


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test placement algorithm')
    parser.add_argument('--config', default='algorithm_config.json', 
                       help='Path to configuration file (default: algorithm_config.json)')
    
    args = parser.parse_args()
    
    test_placement(config_path=args.config)

