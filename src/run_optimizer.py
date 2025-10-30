"""
Fleet Optimization CLI - Predictive Fleet Swap AI
LSP Group Hackathon Solution

Can run using CSV files or database as data source.
Set DATABASE_URL environment variable to use database.
"""
import json
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from models import AssignmentConfig
from optimizer import run_optimization, run_quick_test

console = Console()


def load_config(config_path: str = "algorithm_config.json") -> AssignmentConfig:
    """Load configuration from JSON file"""
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    
    # Calculate max_vehicles_per_location if not specified
    max_vehicles_per_location = cfg['placement'].get('max_vehicles_per_location')
    if max_vehicles_per_location is None:
        # Will be calculated in algorithm based on fleet size
        max_vehicles_per_location = None
    
    return AssignmentConfig(
        # Costs
        relocation_base_cost_pln=cfg['costs']['relocation_base_cost_pln'],
        relocation_per_km_pln=cfg['costs']['relocation_per_km_pln'],
        relocation_per_hour_pln=cfg['costs']['relocation_per_hour_pln'],
        overage_per_km_pln=cfg['costs']['overage_per_km_pln'],
        service_cost_pln=cfg['service_policy'].get('service_cost_pln', 2000.0),
        
        # Service
        service_tolerance_km=cfg['service_policy']['service_tolerance_km'],
        service_duration_hours=cfg['service_policy']['service_duration_hours'],
        service_penalty_pln=cfg['service_policy']['service_penalty_pln'],
        
        # Swap policy
        max_swaps_per_period=cfg['swap_policy']['max_swaps_per_period'],
        swap_period_days=cfg['swap_policy']['swap_period_days'],
        
        # Assignment
        assignment_lookahead_days=cfg['assignment'].get('assignment_lookahead_days', 0),
        look_ahead_days=cfg['assignment'].get('look_ahead_days', 0),
        chain_depth=cfg['assignment'].get('chain_depth', 0),
        chain_weight=cfg['assignment'].get('chain_weight', 10.0),
        max_lookahead_routes=cfg['assignment'].get('max_lookahead_routes', 50),
        use_chain_optimization=cfg['assignment'].get('use_chain_optimization', False),
        assignment_strategy=cfg['assignment'].get('strategy', 'greedy'),
        
        # Placement
        placement_lookahead_days=cfg['placement']['lookahead_days'],
        placement_strategy=cfg['placement'].get('strategy', 'cost_matrix'),
        placement_max_concentration=cfg['placement'].get('max_concentration', 0.30),
        placement_max_vehicles_per_location=max_vehicles_per_location,
        
        # Performance
        use_pathfinding=cfg['performance'].get('use_pathfinding', False),
        use_relation_cache=cfg['performance'].get('use_relation_cache', True),
        progress_report_interval=cfg['performance'].get('progress_report_interval', 1000)
    )


def main():
    """Main CLI entry point"""
    console.print(Panel.fit(
        "[bold cyan]PREDICTIVE FLEET SWAP AI - LSP GROUP[/bold cyan]\n"
        "[white]Fleet Optimization System[/white]",
        border_style="cyan"
    ))
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "full"
    
    # Load configuration
    config_path = "algorithm_config.json"
    if not Path(config_path).exists():
        console.print(f"[bold red]Configuration file not found:[/bold red] {config_path}")
        console.print(f"[yellow]Please create it or copy from algorithm_config.example.json[/yellow]")
        return 1
    
    console.print(f"[dim]Loading configuration from {config_path}[/dim]")
    config = load_config(config_path)
    
    # Check if using database
    use_database = os.getenv('DATABASE_URL') or os.getenv('USE_DATABASE') == '1'
    run_id = None
    
    if use_database:
        console.print("\n[bold cyan]Database mode enabled[/bold cyan] (DATABASE_URL is set)")
        console.print("[dim]Data will be read from and written to the database[/dim]")
        
        # Start a new algorithm run in the database
        from db_adapter import FleetDatabase
        with FleetDatabase() as db:
            run_id = db.start_algorithm_run(config={
                'mode': mode,
                'config_file': config_path
            })
        console.print(f"[dim]Started algorithm run {run_id}[/dim]\n")
        
        data_dir = None  # Signal to use database
    else:
        console.print("\n[bold cyan]CSV mode[/bold cyan] (DATABASE_URL not set)")
        console.print("[dim]Data will be read from CSV files[/dim]")
        
        # Get data directory
        data_dir = "data"
        if not Path(data_dir).exists():
            console.print(f"[bold red]Data directory not found:[/bold red] {data_dir}")
            return 1
    
    output_dir = "output"
    
    # Run optimization
    try:
        if mode == "test" or mode == "quick":
            # Quick test using lookahead windows from config
            console.print("\n[bold yellow]Running test mode[/bold yellow] (using lookahead windows from config)\n")
            run_quick_test(data_dir, output_dir, config, run_id=run_id)
        
        elif mode == "full":
            # Full optimization
            console.print("\n[bold green]Running full optimization...[/bold green]\n")
            run_optimization(data_dir, output_dir, config, run_id=run_id)
        
        else:
            console.print(f"[bold red]Unknown mode:[/bold red] {mode}")
            console.print("\n[bold]Usage:[/bold]")
            console.print("  [green]python src/run_optimizer.py[/green]              # Run full optimization")
            console.print("  [green]python src/run_optimizer.py full[/green]         # Run full optimization")
            console.print("  [green]python src/run_optimizer.py test[/green]         # Run test mode (uses lookahead from config)")
            console.print("  [green]python src/run_optimizer.py quick[/green]        # Same as test")
            console.print("\n[bold]Data Source:[/bold]")
            console.print("  Set [cyan]DATABASE_URL[/cyan] env var to use database")
            console.print("  Otherwise uses CSV files from [cyan]data/[/cyan] directory")
            console.print("\n[bold]Configure lookahead windows in algorithm_config.json:[/bold]")
            console.print("  [cyan]placement_lookahead_days:[/cyan] Routes to analyze for placement")
            console.print("  [cyan]assignment_lookahead_days:[/cyan] Routes to assign")
            return 1
        
        if use_database:
            console.print(f"\n[bold green]Success![/bold green] Results saved to database (run_id={run_id})")
        else:
            console.print("\n[bold green]Success![/bold green] Check the [cyan]output/[/cyan] directory for results.")
        return 0
    
    except Exception as e:
        console.print(f"\n[bold red]Error during optimization: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
