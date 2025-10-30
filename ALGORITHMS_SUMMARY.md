# Fleet Optimization Algorithms - Implementation Summary

## ✅ Latest Updates

**Date**: October 30, 2025

### Key Changes
1. ✅ **Placement now uses lookahead routes only** - Analyzes only first 14 days (configurable)
2. ✅ **All parameters in `algorithm_config.json`** - Centralized configuration
3. ✅ **Clean algorithm separation** - Pure logic in `src/algorithms/`, I/O separate

---

## 📁 Clean Architecture

```
src/
├── algorithms/              # Pure algorithm logic (no I/O)
│   ├── placement.py        # Placement optimization
│   ├── assignment.py       # Route assignment optimization
│   └── __init__.py
│
├── data_loader.py          # Data loading utilities
├── models.py               # Data structures
├── costs.py                # Cost calculation functions
└── constraints.py          # Constraint validation

test_placement.py           # Test runner (separate from algorithms)
algorithm_config.json       # Centralized configuration
```

## 🎯 Placement Algorithm

**Purpose**: Determine optimal initial vehicle placement to minimize relocation costs

**Location**: `src/algorithms/placement.py`

### How It Works

1. **Extract lookahead routes** (first `placement_lookahead_days` only)
2. **Analyze demand** by location
3. **Optimize placement** using selected strategy
4. **Evaluate quality** metrics

### Strategies

#### 1. **Proportional Distribution** (Fast, Simple)
- Allocates vehicles proportionally to demand
- Max `placement_max_concentration` (30%) per location
- **Speed**: < 0.01s
- **Result**: Balanced distribution across ~37 locations

#### 2. **Cost Matrix** (Optimized) ⭐ Recommended
- Builds cost matrix: Cost[vehicle, location]
- Cost inversely proportional to demand
- Greedy assignment minimizing total cost
- **Speed**: ~0.18s
- **Result**: Aggressive clustering in ~4 top locations

### Configuration Parameters

```json
{
  "placement": {
    "strategy": "cost_matrix",           // 'cost_matrix' or 'proportional'
    "lookahead_days": 14,               // Days to analyze for demand
    "max_concentration": 0.30,          // Max 30% of fleet at one location
    "max_vehicles_per_location": null   // null = auto-calculated from max_concentration
  }
}
```

### Test Results (1000 routes, 180 vehicles)

| Strategy | Locations Used | Max Concentration | Est. Cost | Speed |
|----------|---------------|-------------------|-----------|-------|
| Proportional | 37 | 21.7% | 2.05M PLN | 0.00s |
| Cost Matrix | 4 | 30.0% | 2.05M PLN | 0.18s |

Both strategies achieve **excellent cost estimates < 5M PLN** ✅

---

## 🚛 Assignment Algorithm

**Purpose**: Assign vehicles to routes minimizing cost while respecting constraints

**Location**: `src/algorithms/assignment.py`

### Core Logic

**Greedy Strategy**: For each route, assign the cheapest feasible vehicle

### Constraints (Hard)
1. ✅ **Time Feasibility**: Vehicle available + can reach on time
2. ✅ **Contract Limits**: Won't exceed lifetime km
3. ✅ **Swap Policy**: Max `max_swaps_per_period` relocations per `swap_period_days` days

### Cost Components
- **Relocation**: `relocation_base_cost_pln` + distance × `relocation_per_km_pln` + time × `relocation_per_hour_pln`
- **Overage**: (km over annual limit) × `overage_per_km_pln`
- **Service Penalty**: `service_penalty_pln` if service needed soon

### Configuration Parameters

```json
{
  "assignment": {
    "strategy": "greedy",
    "look_ahead_days": 7,
    "chain_depth": 3
  },
  
  "swap_policy": {
    "max_swaps_per_period": 1,          // Max 1 relocation
    "swap_period_days": 90              // Per 90 days (3 months)
  },
  
  "service_policy": {
    "service_tolerance_km": 1000,       // ±1000km tolerance
    "service_duration_hours": 48,       // Service takes 48h
    "service_penalty_pln": 500.0        // Penalty for needing service
  },
  
  "costs": {
    "relocation_base_cost_pln": 1000.0,
    "relocation_per_km_pln": 1.0,
    "relocation_per_hour_pln": 150.0,
    "overage_per_km_pln": 0.92
  }
}
```

### Key Features
- ✅ Respects 1 swap per 90 days limit
- ✅ Only considers direct routes (configurable via `use_pathfinding`)
- ✅ Tracks relocation history per vehicle
- ✅ Updates odometer for both route distance AND relocation distance

---

## 🧪 Testing

### Quick Placement Test
```bash
python test_placement.py --routes 1000 --strategy cost_matrix
python test_placement.py --routes 1000 --strategy proportional
```

### Full System Test
```bash
python src/main.py test 1000   # Test with 1000 routes
python src/main.py full        # Full optimization
```

---

## 📊 Quality Metrics

### Placement Quality
- ✅ Good clustering: 5-30% concentration per location
- ✅ Reasonable cost: < 20M PLN estimated
- ✅ Demand coverage: > 0.1
- ✅ Lookahead routes analyzed: shown in metrics

### Assignment Quality
- ✅ All routes assigned (or < 5% unassigned)
- ✅ Relocation rate < 50%
- ✅ Total cost < 50M PLN
- ✅ Swap policy respected (1 per 90 days)

---

## 🔧 Complete Configuration Reference

**File**: `algorithm_config.json`

```json
{
  "data_dir": "data",
  "output_dir": "output",
  
  "placement": {
    "strategy": "cost_matrix",           // Algorithm: 'cost_matrix' or 'proportional'
    "lookahead_days": 14,               // Only analyze first N days
    "max_concentration": 0.30,          // Max 30% at one location
    "max_vehicles_per_location": null   // null = auto from max_concentration
  },
  
  "assignment": {
    "strategy": "greedy",
    "look_ahead_days": 7,
    "chain_depth": 3
  },
  
  "swap_policy": {
    "max_swaps_per_period": 1,          // Max relocations
    "swap_period_days": 90              // Time period (days)
  },
  
  "service_policy": {
    "service_tolerance_km": 1000,       // Tolerance before service
    "service_duration_hours": 48,       // How long service takes
    "service_penalty_pln": 500.0        // Cost penalty
  },
  
  "costs": {
    "relocation_base_cost_pln": 1000.0,
    "relocation_per_km_pln": 1.0,
    "relocation_per_hour_pln": 150.0,
    "overage_per_km_pln": 0.92
  },
  
  "performance": {
    "progress_report_days": 30,
    "use_pathfinding": false            // Multi-hop routing (slower)
  }
}
```

---

## ✅ Implementation Status

- [x] Placement algorithm (2 strategies)
- [x] **Lookahead routes filtering** ✨ NEW
- [x] Assignment algorithm
- [x] Cost-based optimization
- [x] Swap policy enforcement (1 per 90 days)
- [x] **All parameters in config** ✨ NEW
- [x] Clean code separation (algorithms vs I/O)
- [x] Fast execution (< 1s for placement)
- [x] Comprehensive testing

**Ready for full optimization runs!** 🚀

---

## 📖 Usage Examples

### Test Different Strategies
```bash
# Fast proportional
python test_placement.py --routes 1000 --strategy proportional

# Optimized cost matrix  
python test_placement.py --routes 1000 --strategy cost_matrix
```

### Modify Configuration
Edit `algorithm_config.json`:
```json
{
  "placement": {
    "lookahead_days": 21,        // Increase lookahead window
    "max_concentration": 0.25    // Reduce max per location to 25%
  },
  "swap_policy": {
    "swap_period_days": 60       // Stricter: 60 days instead of 90
  }
}
```

### Run Full Optimization
```bash
python src/main.py full
```

Results saved to `output/` directory with timestamps.
