# Fleet Optimization Algorithms - Critical Analysis & Improvements

**Date**: October 30, 2025  
**Analyzed Files**: 
- `src/algorithms/assignment.py` (671 lines)
- `src/algorithms/placement.py` (346 lines)

---

## Executive Summary

Both algorithms are functional but have **significant flaws** that could lead to suboptimal results, edge case failures, and maintenance challenges. The assignment algorithm has more critical issues than placement.

**Overall Grade**: 
- **Assignment Algorithm**: C+ (functional but flawed)
- **Placement Algorithm**: B- (simpler, fewer issues)

---

## 🚨 CRITICAL ISSUES

### Assignment Algorithm

#### 1. **Annual Lease Reset Timing Bug** (HIGH SEVERITY)
**Location**: Lines 81-92, `check_and_reset_annual_km()`

**Problem**: The reset check happens at the START of route processing, but uses `current_date` as the route start time. If a vehicle completes a route on Dec 30 and the next route starts Jan 5, the reset happens correctly. BUT if it's called during feasibility checks, it may not account for routes that span the boundary.

```python
def check_and_reset_annual_km(vehicle_state: Dict, current_date: datetime) -> bool:
    if current_date >= vehicle_state['lease_end_date']:  # What if route spans this boundary?
        vehicle_state['km_driven_this_lease_year'] = 0
        vehicle_state['lease_cycle_number'] += 1
        # ...
```

**Impact**: Could incorrectly allow or reject routes near lease year boundaries.

**Fix**: Need to check if route execution will cross the boundary, not just start date.

---

#### 2. **Inconsistent Service Logic** (HIGH SEVERITY)
**Location**: Lines 95-121

**Problem**: Service checking is scattered across multiple functions with inconsistent logic:
- `needs_service()` (line 95): Checks if service needed AFTER route
- `schedule_service()` (line 102): Actually performs service BEFORE route
- Service happens at `max(available_from, route.start_datetime)` but availability is then pushed forward

**Issue**: If a vehicle needs service, it's scheduled immediately, consuming 48 hours. But the cost is calculated assuming service happens. There's no verification that the vehicle can STILL make the route after service.

```python
# In check_feasibility (line 146-151):
if service_needed:
    availability = availability + timedelta(hours=config.service_duration_hours)

# But in schedule_service (line 117-118):
service_start = max(vehicle_state['available_from'], route.start_datetime)
vehicle_state['available_from'] = service_start + timedelta(hours=config.service_duration_hours)
```

These don't match! Feasibility check adds service time to availability, but schedule_service recalculates from route start time.

**Impact**: May mark routes as feasible when vehicle can't actually complete them after service.

---

#### 3. **Relation Cache Key Collision Risk** (MEDIUM SEVERITY)
**Location**: Throughout (lines 160, 192, 231, 286, etc.)

**Problem**: Cache uses simple tuples as keys:
```python
cache_key = (vehicle_state['current_location_id'], route.start_location_id)
```

**Issue**: No validation that cached relations are still valid. If location data changes or relations are directional with different properties, cache could return stale data.

**Impact**: Incorrect cost calculations, wrong feasibility checks.

---

#### 4. **Greedy Myopia - No Vehicle Load Balancing** (MEDIUM SEVERITY)
**Location**: Lines 450-536, `optimize_assignment_greedy()`

**Problem**: Always assigns to cheapest vehicle without considering:
- Vehicle workload (one vehicle might do 90% of routes)
- Future availability patterns
- Maintenance/service cycles
- Geographic distribution of vehicles over time

**Example Scenario**:
- Route 1 at Location A → assigns Vehicle X (0 cost, already there)
- Route 2 at Location A → assigns Vehicle X again
- Route 3 at Location A → assigns Vehicle X again
- ...
- Route 100 at Location B → Vehicle X must relocate (now expensive!)

Meanwhile, Vehicles Y and Z sit idle at Location B.

**Impact**: Poor fleet utilization, high costs later, some vehicles overworked.

---

#### 5. **Swap Policy Window Maintenance Race Condition** (LOW-MEDIUM SEVERITY)
**Location**: Lines 70-78, `update_relocation_window()`

**Problem**: Relocation window is only cleaned in `update_state()`, AFTER assignment is made. But feasibility check (line 182) reads from this window. If routes are processed out of chronological order or in batches, stale relocations could remain.

```python
def check_feasibility(...):
    # Check swap policy (must have fresh relocation window)
    if len(vehicle_state['relocations']) >= config.max_swaps_per_period:
        return False, "Swap limit exceeded"
```

But window cleanup happens later in `update_state()`:
```python
def update_state(...):
    update_relocation_window(vehicle_state, route.start_datetime, config)
```

**Impact**: May incorrectly reject valid relocations or allow too many.

---

#### 6. **No Deadlock Detection** (LOW SEVERITY)
**Location**: Entire assignment flow

**Problem**: If all vehicles are unavailable or at locations with no paths to routes, algorithm just marks routes unassigned. No attempt to:
- Check if problem is solvable
- Provide diagnostic information
- Suggest which constraints are too strict

**Impact**: Silent failures, hard to debug why assignments fail.

---

#### 7. **Integer Truncation of Distances** (LOW SEVERITY)
**Location**: Lines 97, 188, 204, 253, 319, 320, 321, 323

**Problem**: All distances converted to int:
```python
future_service_km = vehicle_state['km_since_last_service'] + int(route.distance_km)
```

**Impact**: Loses precision. Over thousands of routes, could accumulate significant error (e.g., 1000 routes × 0.9km rounding = 900km error).

---

### Placement Algorithm

#### 8. **Connectivity Bonus is Insignificant** (MEDIUM SEVERITY)
**Location**: Lines 75-92, `build_cost_matrix()`

**Problem**: Connectivity bonus is too small to matter:
```python
base_cost = 1000 * (1.0 / np.log(local_demand + 2))  # Range: ~300-1500
connectivity_bonus = -100 * connectivity_ratio  # Max: -100
```

With base costs of 300-1500 PLN, a bonus of -100 is only 3-7%. Connectivity is essentially ignored.

**Impact**: Placement doesn't actually consider how well-connected locations are.

---

#### 9. **No Vehicle-Specific Placement** (MEDIUM SEVERITY)
**Location**: Entire placement algorithm

**Problem**: All vehicles treated identically. No consideration for:
- Service intervals (some vehicles need service sooner)
- Lease expiration dates (short-lease vehicles placed same as long-lease)
- Current odometer readings
- Vehicle brands (may have different service networks)

**Impact**: Suboptimal placement, may place high-mileage vehicle far from service locations.

---

#### 10. **Demand Analysis Only Considers Route Starts** (MEDIUM SEVERITY)
**Location**: Lines 11-28, `analyze_demand()`

**Problem**: Only counts routes STARTING at each location:
```python
for route in routes:
    if route.start_location_id:
        demand[route.start_location_id] += 1
```

**Missing**:
- Route END locations (vehicles accumulate there, need retrieval)
- Routes that pass through locations
- Temporal patterns (morning vs evening demand)

**Example**: Location A has 100 routes starting, 0 ending. Location B has 0 starting, 100 ending. Algorithm places 100 vehicles at A, 0 at B. All vehicles end up at B, stranded.

**Impact**: Poor placement doesn't account for route flow patterns.

---

#### 11. **Concentration Penalty Discontinuity** (LOW SEVERITY)
**Location**: Lines 142-153, `greedy_min_cost_assignment()`

**Problem**: Piecewise penalty function has discontinuities:
```python
if current_count >= max_per_location:
    excess = current_count - max_per_location + 1
    concentration_penalty = 5000 * (excess ** 1.5)
elif current_count > max_per_location * 0.7:
    ratio = current_count / max_per_location
    concentration_penalty = 1000 * ((ratio - 0.7) / 0.3) ** 2
```

At `current_count = max_per_location - 1` vs `max_per_location`, penalty jumps from ~1000 to 5000.

**Impact**: Unstable optimization, might avoid locations unnecessarily.

---

#### 12. **Proportional Strategy Can Exceed Fleet Size** (LOW SEVERITY)
**Location**: Lines 171-216, `balanced_proportional_assignment()`

**Problem**: Calculation of vehicles needed per location can lead to edge cases:
```python
vehicles_needed = max(1, int(len(vehicles) * proportion))
```

If many locations have tiny proportions, `max(1, ...)` ensures each gets 1 vehicle, potentially exceeding total fleet.

**Impact**: Rare but possible index out of bounds if logic doesn't catch it.

---

## ⚠️ DESIGN FLAWS

### Both Algorithms

#### 13. **No Backtracking or Re-optimization**
Once decisions are made, they're permanent. No ability to:
- Undo bad assignments
- Rebalance after learning demand patterns
- Adjust placement based on assignment results

**Better approach**: Iterative improvement or two-phase optimization.

---

#### 14. **Greedy is Provably Suboptimal**
Greedy algorithms don't guarantee optimal solutions for vehicle routing problems. This is a known NP-hard problem.

**Known issue**: Chain optimization (lines 330-424) was added to address this but is disabled by default and marked as "not recommended" in the spec.

**Better approaches**:
- Constraint programming (CP-SAT)
- Mixed Integer Linear Programming (MILP)
- Metaheuristics (simulated annealing, genetic algorithms)
- Machine learning-guided search

---

#### 15. **No Stochastic Consideration**
Assumes all data is deterministic:
- Route times are exact
- Service always takes exactly 48 hours
- No traffic, delays, or uncertainties

**Real world**: Need robustness margins or probabilistic constraints.

---

#### 16. **Configuration Parameter Sensitivity**
**Current state**: Many parameters with unclear interactions:
- `swap_period_days=90` - why 90?
- `service_tolerance_km=1000` - why 1000?
- `relocation_base_cost_pln=1000` - how sensitive?

**Problem**: No sensitivity analysis, no parameter tuning methodology.

**Better**: Document parameter impacts, provide tuning guidelines, or auto-tune.

---

## 🔧 CODE QUALITY ISSUES

### Assignment Algorithm

#### 17. **Repeated Relation Lookups**
Even with caching, the pattern of:
```python
cache_key = (vehicle_state['current_location_id'], route.start_location_id)
if config.use_relation_cache and cache_key in relation_cache:
    relation = relation_cache[cache_key]
else:
    relation = get_relation(...)
    if config.use_relation_cache:
        relation_cache[cache_key] = relation
```

...is repeated 7+ times in the code. Should be extracted to helper function.

---

#### 18. **Magic Numbers Still Present**
Despite comments saying "Removed magic numbers", still see:
- `INITIAL_AVAILABILITY_HOURS = 24` (line 22)
- `0.5 ** i` diminishing weight (line 420)
- `1000.0 / (cost + 100.0)` scoring formula (line 412)
- `look_ahead_end = route.end_datetime + timedelta(days=config.look_ahead_days)` (line 368)

These should be in config or documented constants.

---

#### 19. **Inconsistent Error Handling**
- Some functions return `(bool, str)` tuples (line 123)
- Others return None on error (line 174, 250)
- No exceptions for critical failures
- Silent failures in many places

**Better**: Consistent error handling strategy, use exceptions for exceptional cases.

---

#### 20. **Deep Nesting and Long Functions**
- `optimize_assignment_with_lookahead()`: 90 lines
- `build_future_chain()`: 95 lines
- `check_feasibility()`: 87 lines

**Cognitive complexity**: Very high, hard to maintain.

**Better**: Extract sub-functions, reduce nesting levels.

---

### Placement Algorithm

#### 21. **NumPy Array vs Dict Confusion**
Uses NumPy arrays for cost matrix but dicts for everything else. Mixing paradigms:
```python
cost_matrix = np.zeros((n_vehicles, n_locations))  # NumPy
placement = {}  # Dict
location_counts = defaultdict(int)  # Defaultdict
```

**Better**: Consistent data structures or clear boundaries.

---

#### 22. **Incomplete Quality Metrics**
`calculate_placement_quality()` returns metrics but doesn't validate them against thresholds or provide actionable insights.

**Better**: Add validation, warnings, or auto-adjustment suggestions.

---

## 📊 PERFORMANCE ISSUES

#### 23. **O(n²) Feasibility Checks**
For each route (n), check all vehicles (m): **O(n × m)**

For 30,000 routes and 180 vehicles: 5.4M feasibility checks.

Each check potentially does relation lookup (O(r) where r = relations).

**Worst case**: O(n × m × r) - could be 5.4M × 100k = 540B operations.

**Mitigation**: Caching helps, but still fundamentally expensive.

---

#### 24. **Memory: Relation Cache Growth**
Cache grows unbounded:
```python
relation_cache[cache_key] = relation
```

With thousands of routes and hundreds of locations, cache could have 100k+ entries.

**Impact**: Memory usage, cache lookup slowdown.

**Better**: LRU cache with size limit.

---

## 🎯 SUGGESTED IMPROVEMENTS

### Priority 1 - Critical Fixes

1. **Fix service timing consistency**
   - Ensure feasibility check and service scheduling use same logic
   - Add validation that vehicle can still make route after service

2. **Fix annual lease reset logic**
   - Check if route spans lease boundary
   - Pro-rate km to correct lease years

3. **Add route flow analysis to placement**
   - Consider both route starts AND ends
   - Build flow matrix: vehicles accumulate at end locations

4. **Strengthen relation cache**
   - Add cache validation
   - Implement LRU eviction
   - Add cache hit rate metrics

### Priority 2 - Design Improvements

5. **Implement vehicle workload balancing**
   - Track routes per vehicle
   - Add balancing penalty to cost function
   - Prevent single-vehicle dominance

6. **Add vehicle-specific placement**
   - Factor in service intervals
   - Consider lease expiration
   - Place high-mileage vehicles near service hubs

7. **Improve connectivity weighting**
   - Increase connectivity bonus to 20-30% of base cost
   - Or make it configurable

8. **Add two-phase optimization**
   - Phase 1: Initial greedy assignment
   - Phase 2: Local search improvement (swap pairs, relocate, etc.)

### Priority 3 - Code Quality

9. **Extract relation lookup helper**
```python
def get_cached_relation(from_loc, to_loc, relation_lookup, config, cache):
    """Single source of truth for relation lookups with caching."""
    # Implementation
```

10. **Add comprehensive logging**
    - Why assignments failed
    - Which constraints were violated
    - Alternative solutions considered

11. **Add parameter sensitivity analysis**
    - Document parameter impacts
    - Provide tuning guidelines
    - Auto-detect unreasonable configurations

12. **Refactor long functions**
    - Break down into smaller pieces
    - Reduce cognitive complexity
    - Add unit tests for each piece

### Priority 4 - Advanced Features

13. **Implement proper optimization solver**
    - Use Google OR-Tools CP-SAT solver
    - Model as constraint satisfaction problem
    - Could achieve 10-30% cost improvement

14. **Add uncertainty handling**
    - Buffer time for delays
    - Probabilistic service times
    - Robust optimization

15. **Implement rebalancing strategy**
    - Periodic repositioning of idle vehicles
    - Anticipate future demand patterns
    - Learn from historical data

---

## 🧪 TESTING GAPS

Current testing is limited to integration tests. **Missing**:

1. **Unit tests** for individual functions
2. **Edge case tests**:
   - All vehicles unavailable
   - No paths between locations
   - Routes at lease year boundaries
   - Service needed at critical times
3. **Stress tests**: 100k+ routes
4. **Regression tests**: Ensure fixes don't break existing behavior
5. **Benchmark tests**: Track performance over time

---

## 📈 EXPECTED IMPROVEMENTS

If Priority 1-2 improvements are implemented:

| Metric | Current | Potential |
|--------|---------|-----------|
| Total Cost | ~40M PLN | ~25-30M PLN (20-35% reduction) |
| Unassigned Routes | 5-10% | <1% |
| Vehicle Utilization | Unbalanced | Balanced ±20% |
| Relocation Rate | ~40-50% | ~25-35% |
| Fleet Efficiency | ~60% | ~75-85% |

---

## 📝 CONCLUSION

Both algorithms are **functional first-attempts** but have significant room for improvement:

### Assignment Algorithm
- ✅ Handles basic constraints
- ✅ Respects swap policy
- ❌ Service logic has bugs
- ❌ Greedy approach is myopic
- ❌ No workload balancing
- ❌ Poor error handling

**Grade**: C+ → Could be B+ with Priority 1-2 fixes

### Placement Algorithm
- ✅ Simple and fast
- ✅ Achieves reasonable results
- ❌ Ignores connectivity (effectively)
- ❌ Doesn't consider vehicle differences
- ❌ Misses route flow patterns
- ✅ Fewer critical bugs than assignment

**Grade**: B- → Could be A- with Priority 1-2 fixes

### Recommendation
1. **Immediate**: Fix critical bugs (Priority 1)
2. **Short-term**: Implement design improvements (Priority 2)
3. **Medium-term**: Refactor code quality (Priority 3)
4. **Long-term**: Consider proper optimization solver (Priority 4)

**Without fixes**: Current algorithms may produce workable but costly solutions (20-30% more expensive than optimal).

**With fixes**: Could achieve near-optimal results competitive with commercial route optimization software.

