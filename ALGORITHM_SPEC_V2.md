# FLEET OPTIMIZATION ALGORITHM SPECIFICATION V2.0
## STABLE & PRACTICAL IMPLEMENTATION GUIDE

**Date:** October 30, 2025  
**Status:** ✅ Production-Ready  
**Philosophy:** Simple, Fast, Reliable

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Core Principles](#core-principles)
3. [Placement Algorithm Specification](#placement-algorithm-specification)
4. [Assignment Algorithm Specification](#assignment-algorithm-specification)
5. [Data Structures](#data-structures)
6. [Cost Calculations](#cost-calculations)
7. [Constraints & Validation](#constraints--validation)
8. [Performance Requirements](#performance-requirements)
9. [What NOT To Do (Lessons Learned)](#what-not-to-do-lessons-learned)
10. [Testing & Validation](#testing--validation)
11. [Configuration Parameters](#configuration-parameters)
12. [Output Specifications](#output-specifications)

---

## EXECUTIVE SUMMARY

### The Problem
Assign 180 vehicles to 100,000+ routes over 12 months, minimizing costs while respecting constraints.

### The Solution
Two simple, stable algorithms:
1. **Placement Algorithm:** Proportional distribution based on demand
2. **Assignment Algorithm:** Greedy nearest-vehicle with cost minimization

### Success Criteria
- ✅ 100% route completion
- ✅ Reasonable costs (not millions)
- ✅ Fast execution (< 1 hour for full year)
- ✅ Maintainable code
- ✅ Predictable behavior

---

## CORE PRINCIPLES

### 1. **Simplicity Over Complexity**
- Simple algorithms that work > Complex algorithms that fail
- Greedy heuristics that run fast > Optimal solvers that hang
- Understandable code > Clever code

### 2. **Practical Over Theoretical**
- Working system > Perfect optimization
- Fast feedback > Marginal improvements
- Debuggable results > Black box optimization

### 3. **Data-Driven Decisions**
- Let demand drive placement
- Let costs drive assignment
- Let results validate approach

### 4. **Fail-Safe Design**
- Always assign all routes (even if costly)
- Graceful degradation under constraints
- Clear warnings, not silent failures

---

## PLACEMENT ALGORITHM SPECIFICATION

### Purpose
Determine initial location for each vehicle to minimize early relocation costs and position vehicles where demand is highest.

### Strategy: Proportional Distribution

```
INPUT: 
- vehicles: List[Vehicle] (180 vehicles)
- routes: List[Route] (all routes, typically 100k+)
- locations: List[Location] (300 locations)
- lookahead_days: int (default: 14)

OUTPUT:
- placement: Dict[vehicle_id -> location_id]
```

### Algorithm Steps

#### Step 1: Analyze Demand (First N Days)
```python
def analyze_demand(routes, lookahead_days=14):
    """Count routes starting from each location in time window."""
    
    demand = defaultdict(int)
    
    # Get time window
    start_date = parse_datetime(routes[0].start_datetime)
    end_date = start_date + timedelta(days=lookahead_days)
    
    # Count routes per location
    for route in routes:
        if parse_datetime(route.start_datetime) < end_date:
            if route.start_location_id:
                demand[route.start_location_id] += 1
    
    return demand  # {location_id: route_count}
```

**Key Points:**
- Only look at first 14 days (configurable)
- Only count route START locations (where vehicles need to be)
- Simple count, no complex weighting

#### Step 2: Sort Locations by Demand
```python
def sort_locations_by_demand(demand):
    """Sort locations by route count (highest first)."""
    return sorted(demand.items(), key=lambda x: x[1], reverse=True)
```

**Result:** `[(loc_81, 50), (loc_23, 35), (loc_47, 28), ...]`

#### Step 3: Distribute Vehicles Proportionally
```python
def distribute_vehicles(sorted_locations, vehicles):
    """Allocate vehicles proportionally to demand."""
    
    total_demand = sum(count for _, count in sorted_locations)
    placement = {}
    vehicle_index = 0
    
    for loc_id, demand_count in sorted_locations:
        # Calculate proportion
        proportion = demand_count / total_demand
        vehicles_needed = max(1, int(len(vehicles) * proportion))
        
        # Don't over-allocate
        vehicles_needed = min(vehicles_needed, len(vehicles) - vehicle_index)
        
        # Assign vehicles to this location
        for _ in range(vehicles_needed):
            if vehicle_index >= len(vehicles):
                break
            placement[vehicles[vehicle_index].id] = loc_id
            vehicle_index += 1
    
    # Assign remaining vehicles to top location
    if vehicle_index < len(vehicles):
        top_location = sorted_locations[0][0]
        for i in range(vehicle_index, len(vehicles)):
            placement[vehicles[i].id] = top_location
    
    return placement
```

**Expected Results:**
```
High-demand location: 50 routes → 15-20 vehicles
Medium-demand location: 30 routes → 8-12 vehicles
Low-demand location: 10 routes → 2-3 vehicles
Zero-demand location: 0 routes → 0 vehicles
```

### What Makes Good Placement

#### ✅ Good Indicators
- Vehicles clustered at 10-20 high-demand locations
- Top location has 10-25% of fleet
- Zero vehicles at locations with no demand
- Placement cost < 1 million PLN

#### ❌ Bad Indicators
- 1 vehicle per location (scattered)
- All vehicles at one location (over-concentrated)
- Vehicles at locations with no routes
- Placement cost > 10 million PLN

### Edge Cases

#### No Routes in Window
```python
if not demand:
    # Fallback: place all at first hub
    default_location = first_hub.id or locations[0].id
    return {v.id: default_location for v in vehicles}
```

#### More Vehicles Than Demand Locations
```python
# Natural clustering occurs - multiple vehicles per location
# This is GOOD, not a problem
```

#### Highly Unbalanced Demand
```python
# Top location: 80% of routes
# Solution: Cap max vehicles per location at ~30% of fleet
max_per_location = int(len(vehicles) * 0.3)
```

---

## ASSIGNMENT ALGORITHM SPECIFICATION

### Purpose
Assign one vehicle to each route, minimizing total cost (relocations + overages) while respecting constraints.

### Strategy: Greedy Nearest-Vehicle

```
INPUT:
- vehicles: List[Vehicle] (with initial locations)
- routes: List[Route] (sorted by date)
- config: AssignmentConfig (cost params, constraints)

OUTPUT:
- assignments: List[RouteAssignment]
- vehicle_states: Dict[vehicle_id -> VehicleState]
```

### Algorithm Steps

#### Step 1: Initialize Vehicle States
```python
def initialize_vehicle_states(vehicles, start_date):
    """Create runtime state for each vehicle."""
    
    states = {}
    for vehicle in vehicles:
        states[vehicle.id] = VehicleState(
            vehicle_id=vehicle.id,
            current_location_id=vehicle.current_location_id,
            current_odometer_km=vehicle.current_odometer_km,
            km_since_last_service=0,  # Assume just serviced
            km_driven_this_lease_year=0,
            total_lifetime_km=vehicle.current_odometer_km,
            available_from=start_date,
            last_route_id=None,
            lease_cycle_number=1,
            lease_start_date=vehicle.leasing_start_date,
            lease_end_date=vehicle.leasing_end_date,
            relocations_in_window=[],
            annual_limit_km=vehicle.annual_limit,
            service_interval_km=vehicle.service_interval_km,
            total_contract_limit_km=vehicle.total_contract_limit
        )
    
    return states
```

#### Step 2: Process Routes Day-by-Day
```python
def assign_routes_for_day(date, routes_today, vehicle_states, config):
    """Assign all routes for one day."""
    
    assignments = []
    
    # Sort routes by start time
    routes_sorted = sorted(routes_today, key=lambda r: r.start_datetime)
    
    for route in routes_sorted:
        # Find best vehicle for this route
        vehicle_id, cost = find_best_vehicle(route, vehicle_states, config)
        
        if vehicle_id is None:
            print(f"WARNING: No feasible vehicle for route {route.id}")
            continue
        
        # Update vehicle state
        update_vehicle_state(vehicle_states[vehicle_id], route)
        
        # Record assignment
        assignments.append(create_assignment(route, vehicle_id, cost))
    
    return assignments
```

#### Step 3: Find Best Vehicle (Core Logic)
```python
def find_best_vehicle(route, vehicle_states, config):
    """Find vehicle with minimum cost for this route."""
    
    best_vehicle = None
    best_cost = float('inf')
    
    for vehicle_id, state in vehicle_states.items():
        # Check feasibility
        if not is_feasible(state, route, config):
            continue
        
        # Calculate cost
        cost = calculate_assignment_cost(state, route, config)
        
        # Track best
        if cost < best_cost:
            best_cost = cost
            best_vehicle = vehicle_id
    
    return best_vehicle, best_cost
```

### Feasibility Checks

#### Time Feasibility
```python
def is_time_feasible(vehicle_state, route, location_relations):
    """Check if vehicle can reach route start on time."""
    
    # Must be available
    if vehicle_state.available_from > route.start_datetime:
        return False
    
    # If relocation needed, check travel time
    if vehicle_state.current_location_id != route.start_location_id:
        relation = get_relation(
            vehicle_state.current_location_id,
            route.start_location_id,
            location_relations
        )
        
        if relation:
            travel_time = timedelta(hours=relation.time)
            arrival = vehicle_state.available_from + travel_time
            
            if arrival > route.start_datetime:
                return False  # Can't reach in time
    
    return True
```

#### Service Feasibility (Soft)
```python
def needs_service(vehicle_state, route, tolerance_km=1000):
    """Check if vehicle needs service before route."""
    
    km_after_route = vehicle_state.km_since_last_service + route.distance_km
    max_allowed = vehicle_state.service_interval_km + tolerance_km
    
    return km_after_route > max_allowed
```

**Note:** Service need adds cost penalty but doesn't block assignment (fail-safe design).

#### Contract Limit Feasibility (Hard)
```python
def violates_contract_limit(vehicle_state, route):
    """Check if route would exceed lifetime limit."""
    
    if vehicle_state.total_contract_limit_km is None:
        return False  # No lifetime limit
    
    future_km = vehicle_state.total_lifetime_km + route.distance_km
    return future_km > vehicle_state.total_contract_limit_km
```

**Note:** This is a HARD constraint. Never assign route if it violates lifetime limit.

### Cost Calculation

#### Total Assignment Cost
```python
def calculate_assignment_cost(vehicle_state, route, config):
    """Calculate total cost of assigning this vehicle to this route."""
    
    cost = 0.0
    
    # 1. Relocation cost (if needed)
    if vehicle_state.current_location_id != route.start_location_id:
        cost += calculate_relocation_cost(
            vehicle_state.current_location_id,
            route.start_location_id,
            config
        )
    
    # 2. Overage cost (if over annual limit)
    future_annual_km = vehicle_state.km_driven_this_lease_year + route.distance_km
    if future_annual_km > vehicle_state.annual_limit_km:
        overage = future_annual_km - vehicle_state.annual_limit_km
        cost += overage * config.overage_per_km_pln
    
    # 3. Service penalty (if service needed soon)
    if needs_service(vehicle_state, route, config.service_tolerance_km):
        cost += 500  # Small penalty to prefer vehicles not needing service
    
    return cost
```

#### Relocation Cost Formula
```python
def calculate_relocation_cost(from_loc, to_loc, config, location_relations):
    """Calculate cost to relocate vehicle."""
    
    # Get distance and time from relation
    relation = get_relation(from_loc, to_loc, location_relations)
    
    if not relation:
        return 999999.0  # No path = infeasible
    
    cost = (
        config.relocation_base_cost_pln +           # 1000 PLN base
        (relation.dist * config.relocation_per_km_pln) +   # 1.0 PLN/km
        (relation.time * config.relocation_per_hour_pln)   # 150 PLN/hour
    )
    
    return cost
```

**Example:**
```
Relocation: Warsaw (loc_15) → Krakow (loc_23)
Distance: 300 km
Time: 3.5 hours

Cost = 1000 + (300 × 1.0) + (3.5 × 150)
     = 1000 + 300 + 525
     = 1825 PLN
```

### State Updates

#### After Route Assignment
```python
def update_vehicle_state(vehicle_state, route):
    """Update vehicle state after route completion."""
    
    # Update location
    vehicle_state.current_location_id = route.end_location_id
    
    # Update mileage counters
    distance = int(route.distance_km)
    vehicle_state.current_odometer_km += distance
    vehicle_state.km_driven_this_lease_year += distance
    vehicle_state.total_lifetime_km += distance
    vehicle_state.km_since_last_service += distance
    
    # Update availability
    vehicle_state.available_from = route.end_datetime
    vehicle_state.last_route_id = route.id
    
    # Track relocation (if occurred)
    if needs_relocation:
        vehicle_state.relocations_in_window.append(
            (current_date, from_loc, to_loc)
        )
```

---

## DATA STRUCTURES

### Vehicle
```python
@dataclass
class Vehicle:
    id: int
    registration_number: str
    brand: str  # DAF, Scania, Volvo
    service_interval_km: int  # 110k or 120k
    leasing_start_km: int
    leasing_limit_km: int  # Annual or lifetime
    leasing_start_date: str
    leasing_end_date: str
    current_odometer_km: int
    current_location_id: Optional[int]  # None = needs placement
    
    @property
    def has_lifetime_limit(self) -> bool:
        return self.leasing_limit_km > 200000
    
    @property
    def annual_limit(self) -> int:
        if self.leasing_limit_km <= 200000:
            return self.leasing_limit_km
        return 150000  # Standard annual limit
```

### Route
```python
@dataclass
class Route:
    id: int
    start_datetime: str  # ISO format
    end_datetime: str
    distance_km: float
    segments: List[Segment]
    
    @property
    def start_location_id(self) -> Optional[int]:
        return self.segments[0].start_loc_id if self.segments else None
    
    @property
    def end_location_id(self) -> Optional[int]:
        return self.segments[-1].end_loc_id if self.segments else None
    
    @property
    def is_loop(self) -> bool:
        return self.start_location_id == self.end_location_id
```

### VehicleState (Runtime)
```python
@dataclass
class VehicleState:
    vehicle_id: int
    current_location_id: int
    current_odometer_km: int
    km_since_last_service: int
    km_driven_this_lease_year: int  # Resets annually
    total_lifetime_km: int  # Never resets
    available_from: datetime
    last_route_id: Optional[int]
    lease_cycle_number: int
    lease_start_date: datetime
    lease_end_date: datetime
    relocations_in_window: List[Tuple[datetime, int, int]]
    annual_limit_km: int
    service_interval_km: int
    total_contract_limit_km: Optional[int]
```

### RouteAssignment (Output)
```python
@dataclass
class RouteAssignment:
    route_id: int
    vehicle_id: int
    date: str
    route_distance_km: float
    route_start_location: int
    route_end_location: int
    vehicle_km_before: int
    vehicle_km_after: int
    annual_km_before: int
    annual_km_after: int
    requires_relocation: bool
    requires_service: bool
    assignment_cost: float
    chain_preview: str  # Optional: future route preview
```

---

## COST CALCULATIONS

### Relocation Cost
```
Cost_relocation = Base + (Distance × Rate_km) + (Time × Rate_hour)

Where:
  Base = 1,000 PLN
  Distance = km (from location_relations)
  Rate_km = 1.0 PLN/km
  Time = hours (from location_relations)
  Rate_hour = 150 PLN/hour
```

### Overage Cost
```
Cost_overage = (Actual_km - Limit_km) × Penalty_rate

Where:
  Actual_km = km_driven_this_lease_year
  Limit_km = annual_limit_km
  Penalty_rate = 0.92 PLN/km
  
Note: Only applies to annual limits, not lifetime limits
```

### Total Cost
```
Total_Cost = Σ(Relocation_Costs) + Σ(Overage_Costs)

Goal: Minimize Total_Cost
```

---

## CONSTRAINTS & VALIDATION

### Hard Constraints (MUST BE SATISFIED)

#### 1. All Routes Assigned
```python
assert len(assignments) == len(routes), "Some routes unassigned!"
```

#### 2. No Double Assignment
```python
# Vehicle must be available
assert vehicle.available_from <= route.start_datetime
```

#### 3. Lifetime Limit Not Exceeded
```python
if vehicle.total_contract_limit_km:
    assert vehicle.total_lifetime_km <= vehicle.total_contract_limit_km
```

### Soft Constraints (COST PENALTIES)

#### 1. Annual Limit Overage
```python
# Allowed but penalized
if km_driven_this_year > annual_limit:
    cost += (km_driven_this_year - annual_limit) * 0.92
```

#### 2. Service Window
```python
# Allowed within ±1000 km tolerance
if km_since_service > (service_interval + 1000):
    # Should have been serviced earlier
    # Add penalty or force service
```

#### 3. Relocation Frequency
```python
# Configurable limit (default: 1 per 90 days)
# Soft constraint: prefer vehicles with available swaps
```

---

## PERFORMANCE REQUIREMENTS

### Speed Targets
```
Placement: < 1 second for 180 vehicles
Assignment: < 1 hour for 100,000 routes
Total runtime: < 2 hours for full year simulation
```

### Memory Usage
```
< 4 GB RAM for full dataset
Efficient data structures (no unnecessary copies)
```

### Progress Reporting
```python
# Every 30 days
print(f"[*] Progress: {days_processed} days, {routes_assigned} routes")
```

---

## WHAT NOT TO DO (LESSONS LEARNED)

### ❌ DON'T: Use Complex Optimization Algorithms

**What Went Wrong:**
- Hungarian algorithm for placement
- Multi-pass chain optimization
- Result: 116M PLN cost, 1 vehicle per location

**Why It Failed:**
- Over-optimized for wrong objective
- Didn't cluster vehicles naturally
- Too complex to debug
- Computationally expensive

**✅ DO Instead:**
- Simple proportional distribution
- Greedy nearest-vehicle
- Let demand drive placement

### ❌ DON'T: Build Forward Chains for Every Assignment

**What Went Wrong:**
- Built 7-14 day route chains for each vehicle-route pair
- Hung on first day with 174 routes
- Too slow for 100k+ routes

**Why It Failed:**
- O(n²) or worse complexity
- Chain building doesn't help simple greedy
- Over-engineering

**✅ DO Instead:**
- Simple cost calculation per assignment
- No look-ahead (or minimal)
- Fast greedy selection

### ❌ DON'T: Scatter Vehicles Across All Locations

**What Went Wrong:**
- 180 vehicles → 180 locations (1 each)
- Massive relocation costs
- No clustering

**Why It Failed:**
- Misunderstood placement objective
- Treated it as assignment problem (1-to-1 matching)
- Ignored demand patterns

**✅ DO Instead:**
- Cluster vehicles where demand is high
- Multiple vehicles per location (natural)
- Follow demand distribution

### ❌ DON'T: Make Everything Configurable/Cacheable/Extensible

**What Went Wrong:**
- Cache managers
- Pluggable strategies
- Over-abstracted code

**Why It Failed:**
- YAGNI (You Ain't Gonna Need It)
- Adds complexity without value
- Harder to debug

**✅ DO Instead:**
- Simple, direct implementation
- Config only for business parameters
- Easy to read and modify

### ❌ DON'T: Optimize Before Testing

**What Went Wrong:**
- Built "enhanced" algorithms
- Claimed improvements without validation
- Discovered failures only after full implementation

**Why It Failed:**
- No baseline comparison
- Theory ≠ Practice
- Fixed wrong problems

**✅ DO Instead:**
- Test with real data early
- Compare against baseline
- Validate results continuously

---

## TESTING & VALIDATION

### Unit Tests

#### Placement Validation
```python
def test_placement():
    placement = calculate_placement(vehicles, routes, locations)
    
    # All vehicles placed
    assert len(placement) == len(vehicles)
    
    # Clustering at high-demand locations
    location_counts = Counter(placement.values())
    top_location_count = location_counts.most_common(1)[0][1]
    assert top_location_count >= 5  # At least 5 vehicles clustered
    assert top_location_count <= len(vehicles) * 0.3  # Max 30% at one location
    
    # Reasonable cost
    total_cost = estimate_placement_cost(placement)
    assert total_cost < 10_000_000  # Less than 10M PLN
```

#### Assignment Validation
```python
def test_assignment():
    results = run_assignment(vehicles, routes, config)
    
    # All routes assigned
    assert len(results['assignments']) == len(routes)
    
    # No double bookings
    verify_no_conflicts(results['assignments'], results['vehicle_states'])
    
    # Costs reasonable
    assert results['total_cost'] < 100_000_000  # Less than 100M PLN
    
    # Relocations reasonable
    relocations = sum(1 for a in results['assignments'] if a.requires_relocation)
    assert relocations < len(routes) * 0.5  # Less than 50% need relocation
```

### Integration Tests

#### Full Run Test
```bash
# Test with subset
python test_with_1000_routes.py

# Expected results
assert placement_time < 1.0  # seconds
assert assignment_completes == True
assert output_files_generated == True
```

#### Cost Sanity Checks
```python
# Typical ranges for 100k routes, 180 vehicles, 1 year
EXPECTED_RELOCATION_COST = 5_000_000 to 20_000_000 PLN
EXPECTED_OVERAGE_COST = 1_000_000 to 10_000_000 PLN
EXPECTED_TOTAL_COST = 6_000_000 to 30_000_000 PLN

# Red flags
if total_cost > 100_000_000:
    print("ERROR: Cost too high, likely algorithmic failure")
```

---

## CONFIGURATION PARAMETERS

### config.json Structure
```json
{
  "data_dir": "src/data",
  "output_dir": "output",
  
  "placement": {
    "lookahead_days": 14,
    "strategy": "proportional"
  },
  
  "assignment": {
    "strategy": "greedy",
    "look_ahead_days": 0
  },
  
  "swap_policy": {
    "max_swaps_per_period": 1,
    "swap_period_days": 90
  },
  
  "service_policy": {
    "service_window_tolerance_km": 1000,
    "service_duration_hours": 48
  },
  
  "costs": {
    "relocation_base_cost_pln": 1000,
    "relocation_per_km_pln": 1.0,
    "relocation_per_hour_pln": 150.0,
    "overage_per_km_pln": 0.92
  }
}
```

### Parameter Guidelines

#### Lookahead Days (Placement)
```
Too low (< 7): May miss demand patterns
Optimal: 14 days
Too high (> 30): Captures noise, slower computation
```

#### Swap Period
```
Stricter: 60 days (forces better initial placement)
Default: 90 days (balanced)
Looser: 120 days (more flexibility)
```

#### Service Tolerance
```
Tighter: 500 km (more services, less risk)
Default: 1000 km (balanced)
Looser: 1500 km (fewer services, higher risk)
```

---

## OUTPUT SPECIFICATIONS

### Assignments CSV
```csv
route_id,vehicle_id,date,route_distance_km,route_start_location,route_end_location,vehicle_km_before,vehicle_km_after,annual_km_before,annual_km_after,requires_relocation,requires_service,assignment_cost
1,42,2024-01-01,295.5,15,23,50000,50295,0,295,False,False,0.0
2,78,2024-01-01,180.2,23,15,48500,48680,0,180,True,False,1825.0
```

### Vehicle States CSV
```csv
vehicle_id,final_location_id,current_odometer_km,km_driven_this_lease_year,total_lifetime_km,annual_limit_km,overage_km,total_relocations,total_relocation_cost,total_overage_cost
42,23,98450,48450,98450,150000,0,12,18000.0,0.0
78,15,105200,55200,105200,150000,5200,18,24300.0,4784.0
```

### Summary Statistics
```python
{
  'total_routes': 100303,
  'routes_assigned': 100303,
  'routes_unassigned': 0,
  'total_relocations': 3420,
  'total_relocation_cost_pln': 8_450_000,
  'total_overage_cost_pln': 2_100_000,
  'total_cost_pln': 10_550_000,
  'avg_cost_per_route_pln': 105.2,
  'vehicles_over_annual_limit': 23,
  'avg_overage_per_violating_vehicle_km': 4200
}
```

---

## ALGORITHM COMPLEXITY ANALYSIS

### Placement Algorithm
```
Time Complexity: O(R + L log L + V)
Where:
  R = routes in lookahead window (~500-1000)
  L = locations (300)
  V = vehicles (180)

Steps:
  O(R): Count routes per location
  O(L log L): Sort locations by demand
  O(V): Distribute vehicles

Total: ~1ms to 100ms (negligible)
```

### Assignment Algorithm
```
Time Complexity: O(R × V)
Where:
  R = total routes (100,000)
  V = vehicles (180)

Steps per route:
  Check each vehicle: O(V)
  Find minimum cost: O(V)
  Update state: O(1)

Total: 100,000 × 180 = 18M operations
Estimated time: 5-30 minutes (acceptable)
```

---

## MAINTENANCE CHECKLIST

### When Modifying Placement
- [ ] Test on first 1000 routes
- [ ] Verify clustering (not scattering)
- [ ] Check placement cost < 10M PLN
- [ ] Ensure top location has 5-25% of fleet
- [ ] Validate vehicles at demand locations

### When Modifying Assignment
- [ ] Test on subset (1000 routes)
- [ ] Verify all routes assigned
- [ ] Check progress messages appear
- [ ] Validate no infinite loops
- [ ] Ensure reasonable costs

### When Adjusting Costs
- [ ] Document rationale
- [ ] Test impact on small dataset
- [ ] Compare before/after metrics
- [ ] Validate real-world reasonableness

---

## SUMMARY: GOLDEN RULES

### 1. **Keep It Simple**
Complex algorithms fail more often than simple ones.

### 2. **Test Early, Test Often**
Don't wait until full implementation to validate.

### 3. **Let Data Drive Design**
Demand patterns should inform placement.
Cost calculations should inform assignment.

### 4. **Fail-Safe, Not Fail-Hard**
Always complete all routes, even if costly.
Warnings > Errors.

### 5. **Fast Feedback**
Progress messages every 30 days.
Quick tests before full runs.

### 6. **Maintainability Matters**
Code you can debug > Code you can't.
Clear logic > Clever tricks.

### 7. **Know When To Stop**
Good enough > Perfect.
Working > Theoretical optimal.

---

## APPENDIX: QUICK REFERENCE

### Placement: One-Liner
```python
# Count demand, sort, distribute proportionally
placement = distribute_vehicles_by_demand(routes[:14days], vehicles)
```

### Assignment: One-Liner
```python
# For each route, assign cheapest available vehicle
for route in routes:
    vehicle = min(vehicles, key=lambda v: cost(v, route))
```

### Cost: One-Liner
```python
# Relocation + Overage
cost = (1000 + km + hours*150) + (over_limit_km * 0.92)
```

---

## VERSION HISTORY

- **v2.0 (Oct 30, 2025):** Stable, simple algorithms - CURRENT
- **v1.5 (Oct 2025):** Complex "enhanced" version - FAILED
- **v1.0 (Oct 2025):** Initial specification

---

## CONCLUSION

This specification describes a **simple, stable, and practical** approach to fleet optimization.

**It prioritizes:**
- ✅ Working over perfect
- ✅ Fast over optimal
- ✅ Maintainable over clever
- ✅ Practical over theoretical

**The result:**
A system that actually works and produces reasonable results in reasonable time.

**Use this document as:**
- Implementation guide
- Design reference
- Testing checklist
- Troubleshooting resource

---

*End of Algorithm Specification V2.0*

