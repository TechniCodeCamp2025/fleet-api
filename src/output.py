"""
Output generation for optimization results.
"""
import csv
import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from models import RouteAssignment, VehicleState, PlacementResult, AssignmentResult


def write_assignments_csv(
    assignments: List[RouteAssignment],
    output_path: str
) -> None:
    """Write assignments to CSV file"""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'route_id', 'vehicle_id', 'date', 'route_distance_km',
            'route_start_location', 'route_end_location',
            'vehicle_km_before', 'vehicle_km_after',
            'annual_km_before', 'annual_km_after',
            'requires_relocation', 'requires_service', 'assignment_cost',
            'relocation_from', 'relocation_to', 'relocation_distance_km',
            'relocation_time_hours', 'overage_km', 'chain_score'
        ])
        
        # Data
        for a in assignments:
            writer.writerow([
                a.route_id, a.vehicle_id,
                a.date.strftime('%Y-%m-%d %H:%M:%S'),
                f"{a.route_distance_km:.2f}",
                a.route_start_location, a.route_end_location,
                a.vehicle_km_before, a.vehicle_km_after,
                a.annual_km_before, a.annual_km_after,
                a.requires_relocation, a.requires_service,
                f"{a.assignment_cost:.2f}",
                a.relocation_from or '', a.relocation_to or '',
                f"{a.relocation_distance:.2f}",
                f"{a.relocation_time:.2f}",
                a.overage_km,
                f"{a.chain_score:.4f}"
            ])
    
    print(f"[✓] Written {len(assignments)} assignments to {output_path}")


def write_vehicle_states_csv(
    vehicle_states: Dict[int, VehicleState],
    output_path: str
) -> None:
    """Write final vehicle states to CSV"""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'vehicle_id', 'final_location_id', 'current_odometer_km',
            'km_driven_this_lease_year', 'total_lifetime_km',
            'annual_limit_km', 'overage_km', 'overage_ratio',
            'total_relocations', 'total_relocation_cost',
            'total_overage_cost', 'routes_completed',
            'km_since_last_service', 'service_due'
        ])
        
        # Data
        for v_id, state in sorted(vehicle_states.items()):
            overage_km = max(0, state.km_driven_this_lease_year - state.annual_limit_km)
            overage_ratio = state.km_driven_this_lease_year / state.annual_limit_km if state.annual_limit_km > 0 else 0
            service_due = state.km_since_last_service >= state.service_interval_km
            
            writer.writerow([
                v_id, state.current_location_id, state.current_odometer_km,
                state.km_driven_this_lease_year, state.total_lifetime_km,
                state.annual_limit_km, overage_km, f"{overage_ratio:.2%}",
                state.total_relocations, f"{state.total_relocation_cost:.2f}",
                f"{state.total_overage_cost:.2f}", state.routes_completed,
                state.km_since_last_service, service_due
            ])
    
    print(f"[✓] Written {len(vehicle_states)} vehicle states to {output_path}")


def write_vehicles_with_placement_csv(
    vehicles: List,
    placement_result: PlacementResult,
    output_path: str
) -> None:
    """
    Write vehicles CSV with updated Current_location_id from placement results.
    This CSV has the same schema as the input vehicles.csv and can be used
    by the assignment algorithm.
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header - matches vehicles.csv schema exactly
        writer.writerow([
            'Id', 'registration_number', 'brand', 'service_interval_km',
            'Leasing_start_km', 'leasing_limit_km', 'leasing_start_date',
            'leasing_end_date', 'current_odometer_km', 'Current_location_id'
        ])
        
        # Write each vehicle with its assigned location from placement
        for vehicle in vehicles:
            # Get assigned location from placement result
            assigned_location = placement_result.placements.get(vehicle.id, 'N/A')
            
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
                assigned_location
            ])
    
    print(f"[✓] Written {len(vehicles)} vehicles with placement to {output_path}")


def write_placement_report(
    placement_result: PlacementResult,
    output_path: str
) -> None:
    """Write placement analysis report"""
    report = {
        'total_vehicles_placed': placement_result.total_vehicles_placed,
        'locations_used': placement_result.locations_used,
        'avg_vehicles_per_location': round(placement_result.avg_vehicles_per_location, 2),
        'demand_analysis': {
            f"location_{loc_id}": count 
            for loc_id, count in sorted(
                placement_result.demand_analysis.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]  # Top 20 locations
        },
        'placement_distribution': {}
    }
    
    # Count vehicles per location
    from collections import Counter
    location_counts = Counter(placement_result.placements.values())
    report['placement_distribution'] = {
        f"location_{loc_id}": count
        for loc_id, count in location_counts.most_common(20)
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print(f"[✓] Written placement report to {output_path}")


def write_summary_statistics(
    placement_result: PlacementResult,
    assignment_result: AssignmentResult,
    output_path: str,
    runtime_seconds: float
) -> None:
    """Write summary statistics JSON"""
    
    # Vehicle statistics
    vehicles_over_limit = sum(
        1 for s in assignment_result.vehicle_states.values()
        if s.km_driven_this_lease_year > s.annual_limit_km
    )
    
    avg_overage_km = 0
    if vehicles_over_limit > 0:
        total_overage = sum(
            max(0, s.km_driven_this_lease_year - s.annual_limit_km)
            for s in assignment_result.vehicle_states.values()
        )
        avg_overage_km = total_overage / vehicles_over_limit
    
    # Relocation statistics
    relocation_count = sum(
        1 for a in assignment_result.assignments if a.requires_relocation
    )
    relocation_ratio = relocation_count / len(assignment_result.assignments) if assignment_result.assignments else 0
    
    # Cost breakdown
    summary = {
        'execution': {
            'runtime_seconds': round(runtime_seconds, 2),
            'runtime_minutes': round(runtime_seconds / 60, 2),
            'routes_per_second': round(len(assignment_result.assignments) / runtime_seconds, 2) if runtime_seconds > 0 else 0
        },
        'routes': {
            'total_routes': assignment_result.routes_assigned + assignment_result.routes_unassigned,
            'routes_assigned': assignment_result.routes_assigned,
            'routes_unassigned': assignment_result.routes_unassigned,
            'assignment_rate': f"{assignment_result.routes_assigned / (assignment_result.routes_assigned + assignment_result.routes_unassigned) * 100:.2f}%" if assignment_result.routes_assigned + assignment_result.routes_unassigned > 0 else "0%"
        },
        'costs': {
            'total_cost_pln': round(assignment_result.total_cost, 2),
            'relocation_cost_pln': round(assignment_result.total_relocation_cost, 2),
            'overage_cost_pln': round(assignment_result.total_overage_cost, 2),
            'avg_cost_per_route_pln': round(assignment_result.avg_cost_per_route, 2),
            'cost_breakdown': {
                'relocation_percentage': f"{assignment_result.total_relocation_cost / assignment_result.total_cost * 100:.1f}%" if assignment_result.total_cost > 0 else "0%",
                'overage_percentage': f"{assignment_result.total_overage_cost / assignment_result.total_cost * 100:.1f}%" if assignment_result.total_cost > 0 else "0%"
            }
        },
        'relocations': {
            'total_relocations': relocation_count,
            'relocation_ratio': f"{relocation_ratio * 100:.1f}%",
            'avg_relocations_per_vehicle': round(
                sum(s.total_relocations for s in assignment_result.vehicle_states.values()) / len(assignment_result.vehicle_states),
                2
            ) if assignment_result.vehicle_states else 0
        },
        'vehicles': {
            'total_vehicles': len(assignment_result.vehicle_states),
            'vehicles_over_annual_limit': vehicles_over_limit,
            'vehicles_over_limit_percentage': f"{vehicles_over_limit / len(assignment_result.vehicle_states) * 100:.1f}%" if assignment_result.vehicle_states else "0%",
            'avg_overage_per_violating_vehicle_km': round(avg_overage_km, 0),
            'avg_routes_per_vehicle': round(
                sum(s.routes_completed for s in assignment_result.vehicle_states.values()) / len(assignment_result.vehicle_states),
                1
            ) if assignment_result.vehicle_states else 0
        },
        'placement': {
            'vehicles_placed': placement_result.total_vehicles_placed,
            'locations_used': placement_result.locations_used,
            'avg_vehicles_per_location': round(placement_result.avg_vehicles_per_location, 1)
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print(f"[✓] Written summary statistics to {output_path}")
    
    # Print key metrics
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"\n📊 Routes:")
    print(f"   Total: {summary['routes']['total_routes']}")
    print(f"   Assigned: {summary['routes']['routes_assigned']} ({summary['routes']['assignment_rate']})")
    print(f"\n💰 Costs:")
    print(f"   Total: {summary['costs']['total_cost_pln']:,.2f} PLN")
    print(f"   Relocation: {summary['costs']['relocation_cost_pln']:,.2f} PLN ({summary['costs']['cost_breakdown']['relocation_percentage']})")
    print(f"   Overage: {summary['costs']['overage_cost_pln']:,.2f} PLN ({summary['costs']['cost_breakdown']['overage_percentage']})")
    print(f"   Avg per route: {summary['costs']['avg_cost_per_route_pln']:.2f} PLN")
    print(f"\n🚚 Vehicles:")
    print(f"   Total: {summary['vehicles']['total_vehicles']}")
    print(f"   Over limit: {summary['vehicles']['vehicles_over_annual_limit']} ({summary['vehicles']['vehicles_over_limit_percentage']})")
    print(f"   Avg routes/vehicle: {summary['vehicles']['avg_routes_per_vehicle']}")
    print(f"\n🔄 Relocations:")
    print(f"   Total: {summary['relocations']['total_relocations']}")
    print(f"   Ratio: {summary['relocations']['relocation_ratio']}")
    print(f"\n⏱️  Performance:")
    print(f"   Runtime: {summary['execution']['runtime_minutes']:.1f} minutes")
    print(f"   Speed: {summary['execution']['routes_per_second']:.1f} routes/second")
    print("\n" + "="*60 + "\n")


def save_all_results(
    placement_result: PlacementResult,
    assignment_result: AssignmentResult,
    output_dir: str,
    runtime_seconds: float,
    vehicles: List = None
) -> None:
    """Save all results to output directory"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n[*] Saving results to {output_dir}/...")
    
    # Save vehicles with placement (new CSV for assignment input)
    if vehicles:
        write_vehicles_with_placement_csv(
            vehicles,
            placement_result,
            str(output_path / f"vehicles_placed_{timestamp}.csv")
        )
    
    # Save assignments
    write_assignments_csv(
        assignment_result.assignments,
        str(output_path / f"assignments_{timestamp}.csv")
    )
    
    # Save vehicle states
    write_vehicle_states_csv(
        assignment_result.vehicle_states,
        str(output_path / f"vehicle_states_{timestamp}.csv")
    )
    
    # Save placement report
    write_placement_report(
        placement_result,
        str(output_path / f"placement_report_{timestamp}.json")
    )
    
    # Save summary
    write_summary_statistics(
        placement_result,
        assignment_result,
        str(output_path / f"summary_{timestamp}.json"),
        runtime_seconds
    )
    
    print(f"\n[✓] All results saved successfully!")

