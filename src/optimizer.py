"""
Main fleet optimization orchestration.
"""
import time
from typing import Tuple
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from models import AssignmentConfig, PlacementResult, AssignmentResult
from data_loader import load_all_data
from placement_cost_based import calculate_cost_based_placement
from placement import apply_placement_to_vehicles
from assignment import assign_routes
from output import save_all_results
from pathfinding import clear_path_cache

console = Console()


def run_optimization(
    data_dir: str,
    output_dir: str,
    config: AssignmentConfig,
    run_id: int = None
) -> Tuple[PlacementResult, AssignmentResult]:
    """
    Run complete fleet optimization pipeline.
    
    Steps:
    1. Load data
    2. Calculate placement (initial vehicle locations)
    3. Assign routes to vehicles (greedy with look-ahead)
    4. Save results
    
    Args:
        data_dir: Directory containing CSV data files (None = use database)
        output_dir: Directory for output files
        config: Algorithm configuration
        run_id: Optional algorithm run ID for database tracking
    
    Returns:
        (PlacementResult, AssignmentResult)
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]FLEET OPTIMIZATION SYSTEM[/bold cyan]\n"
        "[white]Predictive Fleet Swap AI - LSP Group[/white]",
        border_style="cyan"
    ))
    
    start_time = time.time()
    
    # Clear path cache to prevent memory leak between runs
    clear_path_cache()
    
    # Step 1: Load data
    console.print("\n[bold cyan]STEP 1: LOADING DATA[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        task = progress.add_task("Loading data files...", total=None)
        vehicles, locations, relation_lookup, routes = load_all_data(data_dir)
    
    load_time = time.time() - start_time
    
    # Create data summary table
    data_table = Table(show_header=False, box=None, padding=(0, 2))
    data_table.add_column("Type", style="cyan")
    data_table.add_column("Count", style="green bold")
    data_table.add_row("Vehicles", f"{len(vehicles)}")
    data_table.add_row("Locations", f"{len(locations)}")
    data_table.add_row("Relations", f"{len(relation_lookup)}")
    data_table.add_row("Routes", f"{len(routes)}")
    
    console.print(f"[green]✓[/green] Data loaded in [yellow]{load_time:.2f}s[/yellow]")
    console.print(data_table)
    
    # Step 2: Calculate placement
    console.print("\n[bold cyan]STEP 2: VEHICLE PLACEMENT[/bold cyan]")
    placement_start = time.time()
    
    with console.status("[bold green]Calculating optimal vehicle placement...", spinner="dots"):
        placement_result = calculate_cost_based_placement(
            vehicles, routes, locations, relation_lookup, config
        )
        # Apply placement to vehicles (in-memory)
        apply_placement_to_vehicles(vehicles, placement_result.placements)
        
        # Update vehicle locations in database if using database mode
        if run_id is not None and data_dir is None:
            from db_adapter import FleetDatabase
            with FleetDatabase() as db:
                db.update_vehicle_locations_bulk(placement_result.placements)
    
    placement_time = time.time() - placement_start
    console.print(f"[green]✓[/green] Placement completed in [yellow]{placement_time:.2f}s[/yellow]")
    
    # Step 3: Assign routes
    console.print("\n[bold cyan]STEP 3: ROUTE ASSIGNMENT[/bold cyan]")
    assignment_start = time.time()
    
    with console.status("[bold green]Assigning routes to vehicles...", spinner="dots"):
        assignment_result = assign_routes(
            vehicles, routes, relation_lookup, config
        )
    
    assignment_time = time.time() - assignment_start
    console.print(f"[green]✓[/green] Assignment completed in [yellow]{assignment_time:.2f}s[/yellow]")
    
    # Calculate total time
    total_time = time.time() - start_time
    
    # Step 4: Save results
    console.print("\n[bold cyan]STEP 4: SAVING RESULTS[/bold cyan]")
    save_all_results(
        placement_result,
        assignment_result,
        output_dir,
        total_time,
        vehicles,
        run_id=run_id
    )
    
    # Final summary
    console.print()
    console.print(Panel.fit(
        "[bold green]OPTIMIZATION COMPLETE[/bold green]",
        border_style="green"
    ))
    
    # Timing breakdown table
    timing_table = Table(title="Runtime Breakdown", show_header=True, box=None)
    timing_table.add_column("Phase", style="cyan")
    timing_table.add_column("Time", justify="right", style="yellow")
    timing_table.add_row("Data loading", f"{load_time:.2f}s")
    timing_table.add_row("Placement", f"{placement_time:.2f}s")
    timing_table.add_row("Assignment", f"{assignment_time:.2f}s")
    timing_table.add_row("[bold]Total", f"[bold yellow]{total_time:.2f}s ({total_time/60:.1f} min)")
    
    console.print(timing_table)
    console.print(f"\n[cyan]Performance:[/cyan] [bold]{len(routes)/total_time:.1f}[/bold] routes/second")
    
    # Cost assessment
    if assignment_result.total_cost < 50_000_000:
        console.print(f"\n[green]✓[/green] Total cost [bold green]{assignment_result.total_cost:,.0f} PLN[/bold green] looks reasonable!")
    else:
        console.print(f"\n[yellow]⚠[/yellow] Total cost [bold yellow]{assignment_result.total_cost:,.0f} PLN[/bold yellow] seems high - review results")
    
    # Assignment success
    if assignment_result.routes_unassigned == 0:
        console.print(f"[green]✓[/green] All [bold]{assignment_result.routes_assigned}[/bold] routes successfully assigned!")
    else:
        console.print(f"[yellow]⚠[/yellow] [bold]{assignment_result.routes_unassigned}[/bold] routes could not be assigned")
    
    console.print()
    
    return placement_result, assignment_result


def run_quick_test(
    data_dir: str,
    output_dir: str,
    config: AssignmentConfig,
    run_id: int = None
) -> Tuple[PlacementResult, AssignmentResult]:
    """
    Run optimization using lookahead windows from config.
    Routes processed are determined by placement_lookahead_days and assignment_lookahead_days.
    
    Args:
        data_dir: Directory containing CSV data files (None = use database)
        output_dir: Directory for output files
        config: Algorithm configuration
        run_id: Optional algorithm run ID for database tracking
    """
    console.print(Panel(
        f"[bold]Placement lookahead:[/bold] [cyan]{config.placement_lookahead_days} days[/cyan]\n"
        f"[bold]Assignment lookahead:[/bold] [cyan]{config.assignment_lookahead_days} days[/cyan]",
        title="[yellow]TEST MODE[/yellow]",
        border_style="yellow"
    ))
    
    # Clear path cache to prevent memory leak between runs
    clear_path_cache()
    
    # Load data
    with console.status("[bold green]Loading data...", spinner="dots"):
        vehicles, locations, relation_lookup, routes = load_all_data(data_dir)
    console.print(f"[dim]Loaded {len(routes)} total routes (algorithms will filter by lookahead)[/dim]\n")
    
    start_time = time.time()
    
    # Run placement (will use placement_lookahead_days internally)
    with console.status("[bold green]Calculating placement...", spinner="dots"):
        placement_result = calculate_cost_based_placement(
            vehicles, routes, locations, relation_lookup, config
        )
        apply_placement_to_vehicles(vehicles, placement_result.placements)
        
        # Update vehicle locations in database if using database mode
        if run_id is not None and data_dir is None:
            from db_adapter import FleetDatabase
            with FleetDatabase() as db:
                db.update_vehicle_locations_bulk(placement_result.placements)
    
    # Run assignment (will use assignment_lookahead_days internally)
    with console.status("[bold green]Assigning routes...", spinner="dots"):
        assignment_result = assign_routes(
            vehicles, routes, relation_lookup, config
        )
    
    total_time = time.time() - start_time
    
    # Save results
    save_all_results(placement_result, assignment_result, output_dir, total_time, vehicles, run_id=run_id)
    
    console.print(f"\n[green]✓[/green] Test completed in [yellow]{total_time:.2f}s[/yellow]")
    
    return placement_result, assignment_result

