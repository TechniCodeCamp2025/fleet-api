"""
Main fleet optimization orchestration.
"""
import time
from typing import Tuple

from models import AssignmentConfig, PlacementResult, AssignmentResult
from data_loader import load_all_data
from placement_cost_based import calculate_cost_based_placement
from placement import apply_placement_to_vehicles
from assignment import assign_routes
from output import save_all_results


def run_optimization(
    data_dir: str,
    output_dir: str,
    config: AssignmentConfig
) -> Tuple[PlacementResult, AssignmentResult]:
    """
    Run complete fleet optimization pipeline.
    
    Steps:
    1. Load data
    2. Calculate placement (initial vehicle locations)
    3. Assign routes to vehicles (greedy with look-ahead)
    4. Save results
    
    Args:
        data_dir: Directory containing CSV data files
        output_dir: Directory for output files
        config: Algorithm configuration
    
    Returns:
        (PlacementResult, AssignmentResult)
    """
    print("\n" + "="*80)
    print(" " * 20 + "FLEET OPTIMIZATION SYSTEM")
    print(" " * 15 + "Predictive Fleet Swap AI - LSP Group")
    print("="*80)
    
    start_time = time.time()
    
    # Step 1: Load data
    print("\n🔹 STEP 1: LOADING DATA")
    print("-" * 80)
    vehicles, locations, relation_lookup, routes = load_all_data(data_dir)
    
    load_time = time.time() - start_time
    print(f"\n✅ Data loaded in {load_time:.2f} seconds")
    print(f"   📦 {len(vehicles)} vehicles")
    print(f"   📍 {len(locations)} locations")
    print(f"   🛣️  {len(relation_lookup)} location relations")
    print(f"   🚛 {len(routes)} routes")
    
    # Step 2: Calculate placement
    print("\n🔹 STEP 2: VEHICLE PLACEMENT")
    print("-" * 80)
    placement_start = time.time()
    
    placement_result = calculate_cost_based_placement(
        vehicles, routes, locations, relation_lookup, config
    )
    
    # Apply placement to vehicles
    apply_placement_to_vehicles(vehicles, placement_result.placements)
    
    placement_time = time.time() - placement_start
    print(f"\n✅ Placement completed in {placement_time:.2f} seconds")
    
    # Step 3: Assign routes
    print("\n🔹 STEP 3: ROUTE ASSIGNMENT")
    print("-" * 80)
    assignment_start = time.time()
    
    assignment_result = assign_routes(
        vehicles, routes, relation_lookup, config
    )
    
    assignment_time = time.time() - assignment_start
    print(f"\n✅ Assignment completed in {assignment_time:.2f} seconds")
    
    # Calculate total time
    total_time = time.time() - start_time
    
    # Step 4: Save results
    print("\n🔹 STEP 4: SAVING RESULTS")
    print("-" * 80)
    save_all_results(
        placement_result,
        assignment_result,
        output_dir,
        total_time,
        vehicles
    )
    
    # Final summary
    print("\n" + "="*80)
    print(" " * 25 + "OPTIMIZATION COMPLETE")
    print("="*80)
    print(f"\n⏱️  Total Runtime: {total_time:.2f} seconds ({total_time/60:.1f} minutes)")
    print(f"   - Data loading: {load_time:.2f}s")
    print(f"   - Placement: {placement_time:.2f}s")
    print(f"   - Assignment: {assignment_time:.2f}s")
    print(f"\n📈 Performance: {len(routes)/total_time:.1f} routes/second")
    
    if assignment_result.total_cost < 50_000_000:
        print(f"\n✅ Total cost {assignment_result.total_cost:,.0f} PLN looks reasonable!")
    else:
        print(f"\n⚠️  Total cost {assignment_result.total_cost:,.0f} PLN seems high - review results")
    
    if assignment_result.routes_unassigned == 0:
        print(f"✅ All {assignment_result.routes_assigned} routes successfully assigned!")
    else:
        print(f"⚠️  {assignment_result.routes_unassigned} routes could not be assigned")
    
    print("\n" + "="*80 + "\n")
    
    return placement_result, assignment_result


def run_quick_test(
    data_dir: str,
    output_dir: str,
    config: AssignmentConfig
) -> Tuple[PlacementResult, AssignmentResult]:
    """
    Run optimization using lookahead windows from config.
    Routes processed are determined by placement_lookahead_days and assignment_lookahead_days.
    """
    print(f"\n🧪 TEST MODE\n")
    print(f"   Placement lookahead: {config.placement_lookahead_days} days")
    print(f"   Assignment lookahead: {config.assignment_lookahead_days} days")
    print()
    
    # Load data
    vehicles, locations, relation_lookup, routes = load_all_data(data_dir)
    print(f"[*] Loaded {len(routes)} total routes (algorithms will filter by lookahead)\n")
    
    start_time = time.time()
    
    # Run placement (will use placement_lookahead_days internally)
    placement_result = calculate_cost_based_placement(
        vehicles, routes, locations, relation_lookup, config
    )
    apply_placement_to_vehicles(vehicles, placement_result.placements)
    
    # Run assignment (will use assignment_lookahead_days internally)
    assignment_result = assign_routes(
        vehicles, routes, relation_lookup, config
    )
    
    total_time = time.time() - start_time
    
    # Save results
    save_all_results(placement_result, assignment_result, output_dir, total_time, vehicles)
    
    print(f"\n✅ Test completed in {total_time:.2f} seconds")
    
    return placement_result, assignment_result

