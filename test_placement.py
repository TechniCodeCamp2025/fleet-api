#!/usr/bin/env python3
"""
Simple test runner for placement algorithm.
Separated from algorithm logic for clarity.
"""
import sys
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


def test_placement(data_dir='data', num_routes=None, strategy='cost_matrix'):
    """Test placement algorithm."""
    
    print_separator("PLACEMENT ALGORITHM TEST")
    
    # Load data
    print("\n[1/4] Loading data...")
    start = time.time()
    vehicles, locations, relation_lookup, routes = load_all_data(data_dir)
    print(f"   ✓ Loaded in {time.time()-start:.2f}s")
    print(f"   • {len(vehicles)} vehicles")
    print(f"   • {len(locations)} locations")
    print(f"   • {len(routes)} routes")
    
    # Subset if requested
    if num_routes:
        routes = routes[:num_routes]
        print(f"   • Using first {len(routes)} routes for test")
    
    # Config
    config = AssignmentConfig(
        placement_lookahead_days=14,
        swap_period_days=90,
        relocation_base_cost_pln=1000,
        relocation_per_km_pln=1.0,
        relocation_per_hour_pln=150,
        overage_per_km_pln=0.92,
        service_tolerance_km=1000,
        service_penalty_pln=500
    )
    
    # Run placement
    print(f"\n[2/4] Running placement algorithm (strategy: {strategy})...")
    start = time.time()
    placement, quality = optimize_placement(
        vehicles, routes, relation_lookup, config, strategy=strategy
    )
    elapsed = time.time() - start
    print(f"   ✓ Completed in {elapsed:.2f}s")
    
    # Show results
    print(f"\n[3/4] Placement Results:")
    print(f"   • Vehicles placed: {quality['total_vehicles']}")
    print(f"   • Locations used: {quality['locations_used']}")
    print(f"   • Max concentration: {quality['max_concentration']:.1%}")
    print(f"   • Demand coverage: {quality['demand_coverage']:.3f}")
    print(f"   • Estimated relocation cost: {quality['estimated_relocation_cost']:,.0f} PLN")
    
    # Show distribution
    print(f"\n[4/4] Vehicle Distribution (Top 10 locations):")
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
    
    if quality['estimated_relocation_cost'] < 5_000_000:
        print("   ✅ Excellent cost estimate (< 5M PLN)")
    elif quality['estimated_relocation_cost'] < 20_000_000:
        print("   ✅ Good cost estimate (< 20M PLN)")
    else:
        print("   ⚠️  High estimated costs")
    
    print("\n✨ Test complete!\n")
    
    return placement, quality


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test placement algorithm')
    parser.add_argument('--routes', type=int, default=1000, help='Number of routes to test')
    parser.add_argument('--strategy', choices=['cost_matrix', 'proportional'], 
                       default='cost_matrix', help='Placement strategy')
    
    args = parser.parse_args()
    
    test_placement(num_routes=args.routes, strategy=args.strategy)

