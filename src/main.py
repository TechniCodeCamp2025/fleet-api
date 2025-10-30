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
        
        # Assignment
        look_ahead_days=cfg['assignment']['look_ahead_days'],
        chain_depth=cfg['assignment']['chain_depth'],
        
        # Placement
        placement_lookahead_days=cfg['placement']['lookahead_days']
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
            # Quick test with 1000 routes
            num_routes = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
            print(f"\n🧪 Running quick test with {num_routes} routes...\n")
            run_quick_test(data_dir, output_dir, config, num_routes)
        
        elif mode == "full":
            # Full optimization
            print(f"\n🚀 Running full optimization...\n")
            run_optimization(data_dir, output_dir, config)
        
        else:
            print(f"❌ Unknown mode: {mode}")
            print(f"\nUsage:")
            print(f"  python main.py              # Run full optimization")
            print(f"  python main.py full         # Run full optimization")
            print(f"  python main.py test [N]     # Run test with N routes (default: 1000)")
            print(f"  python main.py quick [N]    # Same as test")
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
