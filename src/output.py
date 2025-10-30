"""
Output generation for optimization results.
Supports both CSV and database output.
"""
import csv
import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import os
from rich.console import Console
from rich.table import Table

from models import RouteAssignment, VehicleState, PlacementResult, AssignmentResult

console = Console()


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
    
    console.print(f"[green]✓[/green] Written {len(assignments)} assignments to [cyan]{output_path}[/cyan]")


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
    
    console.print(f"[green]✓[/green] Written {len(vehicle_states)} vehicle states to [cyan]{output_path}[/cyan]")


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
    
    console.print(f"[green]✓[/green] Written {len(vehicles)} vehicles with placement to [cyan]{output_path}[/cyan]")


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
    
    console.print(f"[green]✓[/green] Written placement report to [cyan]{output_path}[/cyan]")


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
    
    console.print(f"[green]✓[/green] Written summary statistics to [cyan]{output_path}[/cyan]")
    
    # Print key metrics in a nice table
    console.print("\n[bold cyan]SUMMARY STATISTICS[/bold cyan]")
    
    # Routes table
    routes_table = Table(title="Routes", show_header=False, box=None, padding=(0, 2))
    routes_table.add_column("Metric", style="cyan")
    routes_table.add_column("Value", style="white")
    routes_table.add_row("Total", str(summary['routes']['total_routes']))
    routes_table.add_row("Assigned", f"{summary['routes']['routes_assigned']} ({summary['routes']['assignment_rate']})")
    console.print(routes_table)
    
    # Costs table
    costs_table = Table(title="Costs", show_header=False, box=None, padding=(0, 2))
    costs_table.add_column("Metric", style="cyan")
    costs_table.add_column("Value", style="green")
    costs_table.add_row("Total", f"{summary['costs']['total_cost_pln']:,.2f} PLN")
    costs_table.add_row("Relocation", f"{summary['costs']['relocation_cost_pln']:,.2f} PLN ({summary['costs']['cost_breakdown']['relocation_percentage']})")
    costs_table.add_row("Overage", f"{summary['costs']['overage_cost_pln']:,.2f} PLN ({summary['costs']['cost_breakdown']['overage_percentage']})")
    costs_table.add_row("Avg/route", f"{summary['costs']['avg_cost_per_route_pln']:.2f} PLN")
    console.print(costs_table)
    
    # Vehicles table
    vehicles_table = Table(title="Vehicles", show_header=False, box=None, padding=(0, 2))
    vehicles_table.add_column("Metric", style="cyan")
    vehicles_table.add_column("Value", style="white")
    vehicles_table.add_row("Total", str(summary['vehicles']['total_vehicles']))
    vehicles_table.add_row("Over limit", f"{summary['vehicles']['vehicles_over_annual_limit']} ({summary['vehicles']['vehicles_over_limit_percentage']})")
    vehicles_table.add_row("Avg routes", str(summary['vehicles']['avg_routes_per_vehicle']))
    console.print(vehicles_table)
    
    # Relocations and Performance
    misc_table = Table(title="Relocations & Performance", show_header=False, box=None, padding=(0, 2))
    misc_table.add_column("Metric", style="cyan")
    misc_table.add_column("Value", style="white")
    misc_table.add_row("Total relocations", str(summary['relocations']['total_relocations']))
    misc_table.add_row("Relocation ratio", summary['relocations']['relocation_ratio'])
    misc_table.add_row("Runtime", f"{summary['execution']['runtime_minutes']:.1f} minutes")
    misc_table.add_row("Speed", f"{summary['execution']['routes_per_second']:.1f} routes/second")
    console.print(misc_table)
    console.print()


def save_placement_results(
    placement_result: PlacementResult,
    vehicles: List = None,
    run_id: int = None
) -> int:
    """
    Save placement results to database.
    
    Args:
        placement_result: Placement algorithm result
        vehicles: List of vehicles with placement applied
        run_id: Algorithm run ID for database tracking
    
    Returns:
        run_id if saved to database
    """
    from db_adapter import FleetDatabase
    
    console.print("[dim]Saving placement results to database...[/dim]")
    
    with FleetDatabase() as db:
        if run_id is None:
            # Start a new run if not provided
            run_id = db.start_algorithm_run(config={'algorithm': 'placement'})
        
        # Save vehicle placements to database
        # Update vehicle current locations
        for vehicle_id, location_id in placement_result.placements.items():
            db.cursor.execute(
                "UPDATE vehicles SET current_location_id = ? WHERE id = ?",
                (location_id, vehicle_id)
            )
        
        db.conn.commit()
        
        # Complete the run
        db.complete_algorithm_run(
            run_id,
            routes_processed=0,  # Placement doesn't process routes
            assignments_created=0,
            total_cost=placement_result.total_cost
        )
    
    console.print(f"[green]✓[/green] Placement results saved to database (run_id=[cyan]{run_id}[/cyan])")
    return run_id


def save_assignment_results(
    assignment_result: AssignmentResult,
    vehicles: List = None,
    run_id: int = None
) -> int:
    """
    Save assignment results to database.
    
    Args:
        assignment_result: Assignment algorithm result
        vehicles: List of vehicles with assignments
        run_id: Algorithm run ID for database tracking
    
    Returns:
        run_id if saved to database
    """
    from db_adapter import FleetDatabase
    
    console.print("[dim]Saving assignment results to database...[/dim]")
    
    with FleetDatabase() as db:
        if run_id is None:
            # Start a new run if not provided
            run_id = db.start_algorithm_run(config={'algorithm': 'assignment'})
        
        # Save all assignments and vehicle states
        db.save_all_results(
            assignment_result.assignments,
            assignment_result.vehicle_states,
            run_id
        )
        
        # Complete the run
        db.complete_algorithm_run(
            run_id,
            routes_processed=assignment_result.routes_assigned + assignment_result.routes_unassigned,
            assignments_created=assignment_result.routes_assigned,
            total_cost=assignment_result.total_cost
        )
    
    console.print(f"[green]✓[/green] Assignment results saved to database (run_id=[cyan]{run_id}[/cyan])")
    return run_id


def save_all_results(
    placement_result: PlacementResult,
    assignment_result: AssignmentResult,
    output_dir: str,
    runtime_seconds: float,
    vehicles: List = None,
    run_id: int = None
) -> int:
    """
    Save all results to database and/or output directory.
    If run_id is provided or USE_DATABASE env var is set, save to database.
    Otherwise save to CSV files.
    
    Returns:
        run_id if saved to database, None if saved to CSV
    """
    # If run_id provided or USE_DATABASE set, save to database
    if run_id is not None or os.getenv('USE_DATABASE') == '1':
        console.print("[dim]Saving results to database...[/dim]")
        from db_adapter import FleetDatabase
        
        with FleetDatabase() as db:
            if run_id is None:
                # Start a new run if not provided
                run_id = db.start_algorithm_run()
            
            # Save all assignments and vehicle states
            db.save_all_results(
                assignment_result.assignments,
                assignment_result.vehicle_states,
                run_id
            )
            
            # Complete the run
            db.complete_algorithm_run(
                run_id,
                routes_processed=assignment_result.routes_assigned + assignment_result.routes_unassigned,
                assignments_created=assignment_result.routes_assigned,
                total_cost=assignment_result.total_cost
            )
        
        console.print(f"[green]✓[/green] Results saved to database (run_id=[cyan]{run_id}[/cyan])")
        return run_id
    
    # Otherwise save to CSV (backward compatibility)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    console.print(f"\n[dim]Saving results to {output_dir}/...[/dim]")
    
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
    
    console.print(f"\n[bold green]✓ All results saved successfully![/bold green]")
    return None

