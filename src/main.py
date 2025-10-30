"""
Fleet Optimization CLI - Predictive Fleet Swap AI
LSP Group Hackathon Solution
"""
import json
import sys
from pathlib import Path

from models import AssignmentConfig
from optimizer import run_optimization, run_quick_test


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
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║         PREDICTIVE FLEET SWAP AI - LSP GROUP                 ║
║         Fleet Optimization System                             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "full"
    
    # Load configuration
    config_path = "algorithm_config.json"
    if not Path(config_path).exists():
        print(f"❌ Configuration file not found: {config_path}")
        print(f"   Please create it or copy from algorithm_config.example.json")
        return 1
    
    print(f"[*] Loading configuration from {config_path}")
    config = load_config(config_path)
    
    # Get data directory
    data_dir = "data"
    if not Path(data_dir).exists():
        print(f"❌ Data directory not found: {data_dir}")
        return 1
    
    output_dir = "output"
    
    # Run optimization
    try:
        if mode == "test" or mode == "quick":
            # Quick test using lookahead windows from config
            print(f"\n🧪 Running test mode (using lookahead windows from config)...\n")
            run_quick_test(data_dir, output_dir, config)
        
        elif mode == "full":
            # Full optimization
            print(f"\n🚀 Running full optimization...\n")
            run_optimization(data_dir, output_dir, config)
        
        else:
            print(f"❌ Unknown mode: {mode}")
            print(f"\nUsage:")
            print(f"  python main.py              # Run full optimization")
            print(f"  python main.py full         # Run full optimization")
            print(f"  python main.py test         # Run test mode (uses lookahead from config)")
            print(f"  python main.py quick        # Same as test")
            print(f"\nConfigure lookahead windows in algorithm_config.json:")
            print(f"  - placement_lookahead_days: Routes to analyze for placement")
            print(f"  - assignment_lookahead_days: Routes to assign")
            return 1
        
        print("\n✨ Success! Check the output/ directory for results.")
        return 0
    
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
