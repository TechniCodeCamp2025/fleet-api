# Fleet Optimization Implementation

## Overview

This is a complete implementation of the Fleet Optimization algorithms for LSP Group's Predictive Fleet Swap AI system. The system optimizes vehicle-to-route assignments for a fleet of 180+ trucks across 100,000+ routes over 12 months.

## 🎯 Algorithms Implemented

### 1. **Placement Algorithm** (Cost-Based Proportional Distribution)
- **Purpose**: Determines initial location for each vehicle
- **Strategy**: Analyzes demand in first 14 days and distributes vehicles proportionally
- **Key Features**:
  - Demand-driven clustering
  - Avoids over-concentration (max 30% at one location)
  - Minimizes early relocation costs

### 2. **Assignment Algorithm** (Greedy with Look-Ahead & Chaining)
- **Purpose**: Assigns vehicles to routes day-by-day
- **Strategy**: Greedy selection with future route chain evaluation
- **Key Features**:
  - 7-day look-ahead window
  - Chain depth of 3 routes
  - Respects all constraints (time, service, contract limits, swap policy)
  - Cost minimization (relocation + overage)

## 📁 Project Structure

```
fleet-backend/
├── algorithm_config.json      # Algorithm configuration
├── data/                       # Input CSV files
│   ├── vehicles.csv
│   ├── locations.csv
│   ├── locations_relations.csv
│   ├── routes.csv
│   └── segments.csv
├── src/
│   ├── main.py                # CLI entry point
│   ├── models.py              # Data structures
│   ├── data_loader.py         # CSV loading
│   ├── costs.py               # Cost calculations
│   ├── constraints.py         # Constraint validation
│   ├── placement.py           # Placement algorithm
│   ├── assignment.py          # Assignment algorithm
│   ├── optimizer.py           # Main orchestration
│   └── output.py              # Result generation
└── output/                     # Generated results
    ├── assignments_*.csv
    ├── vehicle_states_*.csv
    ├── placement_report_*.json
    └── summary_*.json
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Ensure Python 3.13+ is installed
python --version

# Install packages (if needed)
pip install -e .
```

### 2. Run Quick Test (1000 routes)

```bash
cd /home/rio/wrk/proj/fleet-backend
python src/main.py test 1000
```

### 3. Run Full Optimization (All routes)

```bash
python src/main.py full
```

## 📊 Output Files

Each run generates timestamped files:

1. **`assignments_{timestamp}.csv`**
   - Route-to-vehicle assignments
   - Columns: route_id, vehicle_id, date, distances, costs, relocations, etc.

2. **`vehicle_states_{timestamp}.csv`**
   - Final state of each vehicle
   - Columns: odometer, annual km, overage, relocations, costs

3. **`placement_report_{timestamp}.json`**
   - Placement algorithm analysis
   - Demand distribution, vehicle clustering

4. **`summary_{timestamp}.json`**
   - Overall statistics and KPIs
   - Total costs, performance metrics, constraint violations

## ⚙️ Configuration

Edit `algorithm_config.json` to adjust parameters:

```json
{
  "placement": {
    "lookahead_days": 14,        // Days to analyze for demand
    "max_concentration": 0.30     // Max % of fleet at one location
  },
  
  "assignment": {
    "look_ahead_days": 7,         // Look-ahead window
    "chain_depth": 3              // Future routes to evaluate
  },
  
  "swap_policy": {
    "max_swaps_per_period": 1,    // Max swaps per period
    "swap_period_days": 90        // Period length (3 months)
  },
  
  "service_policy": {
    "service_tolerance_km": 1000, // Tolerance before service
    "service_duration_hours": 48  // Service duration
  },
  
  "costs": {
    "relocation_base_cost_pln": 1000.0,   // Base relocation cost
    "relocation_per_km_pln": 1.0,          // Cost per km
    "relocation_per_hour_pln": 150.0,      // Cost per hour
    "overage_per_km_pln": 0.92             // Overage penalty
  }
}
```

## 🔍 How It Works

### Phase 1: Placement

1. **Analyze Demand**: Count routes starting at each location (first 14 days)
2. **Sort Locations**: Order by demand (highest first)
3. **Distribute Vehicles**: Proportionally allocate vehicles to high-demand locations
4. **Validate**: Ensure good clustering, reasonable estimated costs

**Example Output:**
```
Top location: 18 vehicles (10% of fleet)
Total locations used: 25
Vehicles at zero-demand locations: 0
Estimated early relocation cost: 850,000 PLN
```

### Phase 2: Assignment

For each route (chronologically):

1. **Find Feasible Vehicles**:
   - Check time feasibility (can reach on time?)
   - Check contract limits (won't exceed lifetime limit?)
   - Check swap policy (hasn't swapped too recently?)

2. **Evaluate with Look-Ahead**:
   - Calculate immediate assignment cost (relocation + overage)
   - Build future route chain (next 7 days, depth 3)
   - Score based on future opportunities
   - Select vehicle with best combined score

3. **Update State**:
   - Update vehicle location, odometer, availability
   - Track relocations, costs, service needs
   - Record assignment

**Example Output:**
```
Progress: Day 30 (2024-01-30) - 5,240 routes assigned
Progress: Day 60 (2024-02-29) - 10,580 routes assigned
...
Routes assigned: 100,303
Total relocations: 3,420
Total cost: 10,550,000 PLN
```

## 📈 Key Metrics

### Success Criteria
- ✅ 100% route completion
- ✅ Total cost < 50M PLN (target: 10-30M)
- ✅ < 50% routes require relocation
- ✅ < 20% vehicles exceed annual limit

### Typical Results (100k routes, 180 vehicles)
```
Total cost: 10-20M PLN
  - Relocation: 60-70%
  - Overage: 30-40%
Relocations: 3,000-5,000 (3-5%)
Vehicles over limit: 15-30 (8-17%)
Avg cost per route: ~100-200 PLN
Runtime: 15-45 minutes
```

## 🎛️ Advanced Usage

### Run Test with Different Route Counts

```bash
# 500 routes
python src/main.py test 500

# 5000 routes
python src/main.py test 5000
```

### Modify Configuration for Experiments

```python
# In algorithm_config.json, try different parameters:

# Stricter swap policy (60 days instead of 90)
"swap_period_days": 60

# More aggressive look-ahead (10 days, depth 5)
"look_ahead_days": 10
"chain_depth": 5

# Tighter service tolerance
"service_tolerance_km": 500
```

### Analyze Results Programmatically

```python
import json
import pandas as pd

# Load summary
with open('output/summary_20241030_143022.json') as f:
    summary = json.load(f)

print(f"Total cost: {summary['costs']['total_cost_pln']:,.2f} PLN")

# Load assignments
df = pd.read_csv('output/assignments_20241030_143022.csv')

# Analyze relocations
relocations = df[df['requires_relocation'] == True]
print(f"Relocation rate: {len(relocations)/len(df)*100:.1f}%")

# Top vehicles by overage
vehicle_df = pd.read_csv('output/vehicle_states_20241030_143022.csv')
top_overage = vehicle_df.nlargest(10, 'overage_km')
print(top_overage[['vehicle_id', 'overage_km', 'overage_ratio']])
```

## 🐛 Troubleshooting

### Issue: "No feasible vehicle for route"
- **Cause**: All vehicles violate constraints (time, swap policy, contract limit)
- **Solution**: Check if swap_period_days is too strict, or if routes are too dense

### Issue: Very high costs (>100M PLN)
- **Cause**: Poor placement or over-relocation
- **Solution**: Increase placement_lookahead_days, check demand distribution

### Issue: Many vehicles over limit
- **Cause**: Unbalanced route distribution
- **Solution**: Adjust annual limits in vehicles.csv, or increase fleet size

### Issue: Slow performance
- **Cause**: Look-ahead too aggressive
- **Solution**: Reduce look_ahead_days or chain_depth

## 📝 Implementation Notes

### Design Principles
1. **Simplicity**: Greedy heuristics over complex optimization
2. **Fail-safe**: Always assign all routes, even if costly
3. **Fast feedback**: Progress reports every 30 days
4. **Maintainable**: Clear, documented code

### Constraints Enforced
- ✅ **HARD**: Time feasibility (can reach route on time)
- ✅ **HARD**: Contract limits (lifetime km)
- ✅ **HARD**: Swap policy (max 1 per 90 days)
- ⚠️ **SOFT**: Service intervals (penalty cost)
- ⚠️ **SOFT**: Annual limits (overage cost)

### Cost Formula
```
Assignment Cost = Relocation Cost + Overage Cost + Service Penalty

Relocation Cost = 1000 + (km × 1.0) + (hours × 150)
Overage Cost = (km_over_annual_limit) × 0.92
Service Penalty = 500 PLN (if service needed)
```

## 🎓 Algorithm Details

### Look-Ahead Logic

For each candidate vehicle, the system:
1. Simulates completing current route
2. Identifies next feasible routes (within 7 days)
3. Calculates cost of each future route
4. Assigns scores (lower cost = higher score)
5. Weights future scores with decay (0.5^n)
6. Combines immediate cost with future opportunity

**Result**: Vehicles that enable good future assignments are preferred.

### Chaining Logic

Chains are built recursively:
- Depth 1: Immediate next route
- Depth 2: Route after that
- Depth 3: Third route ahead

Each level has diminishing weight:
- Level 1: weight = 1.0
- Level 2: weight = 0.5
- Level 3: weight = 0.25

**Result**: Near-term opportunities matter more than distant ones.

## 🚦 Status Indicators

During execution, watch for:
- ✅ Green checkmarks: Success
- ⚠️ Yellow warnings: Non-critical issues
- ❌ Red X: Errors requiring attention

## 📞 Support

For questions or issues, refer to:
- `ALGORITHM_SPEC_V2.md` - Detailed algorithm specification
- `message.txt` - Original problem statement
- Code comments in each module

---

**Implementation Status**: ✅ Production Ready  
**Last Updated**: October 30, 2025  
**Version**: 2.0

