"""
Data models for fleet optimization system.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from enum import Enum


class VehicleBrand(Enum):
    DAF = "DAF"
    SCANIA = "Scania"
    VOLVO = "Volvo"


@dataclass
class Vehicle:
    """Vehicle entity from vehicles.csv"""
    id: int
    registration_number: str
    brand: str
    service_interval_km: int
    leasing_start_km: int
    leasing_limit_km: int  # Can be annual OR lifetime total
    leasing_start_date: datetime
    leasing_end_date: datetime
    current_odometer_km: int
    current_location_id: Optional[int] = None
    
    @property
    def has_lifetime_limit(self) -> bool:
        """Determine if limit is lifetime (>200k) or annual"""
        return self.leasing_limit_km > 200000
    
    @property
    def annual_limit_km(self) -> int:
        """Get annual limit"""
        if self.has_lifetime_limit:
            return 150000  # Default annual
        return self.leasing_limit_km
    
    @property
    def total_contract_limit_km(self) -> Optional[int]:
        """Get total contract limit if applicable"""
        if self.has_lifetime_limit:
            return self.leasing_limit_km
        return None


@dataclass
class Location:
    """Location entity from locations.csv"""
    id: int
    name: str
    lat: float
    long: float
    is_hub: bool


@dataclass
class LocationRelation:
    """Relation between locations from locations_relations.csv"""
    id: int
    id_loc_1: int
    id_loc_2: int
    dist: float  # kilometers
    time: float  # hours


@dataclass
class Segment:
    """Route segment from segments.csv"""
    id: int
    route_id: int
    seq: int
    start_loc_id: int
    end_loc_id: int
    start_datetime: datetime
    end_datetime: datetime
    distance_travelled_km: float
    relation_id: int


@dataclass
class Route:
    """Route entity from routes.csv with segments"""
    id: int
    start_datetime: datetime
    end_datetime: datetime
    distance_km: float
    segments: List[Segment] = field(default_factory=list)
    
    @property
    def start_location_id(self) -> Optional[int]:
        """Get starting location from first segment"""
        return self.segments[0].start_loc_id if self.segments else None
    
    @property
    def end_location_id(self) -> Optional[int]:
        """Get ending location from last segment"""
        return self.segments[-1].end_loc_id if self.segments else None
    
    @property
    def is_loop(self) -> bool:
        """Check if route starts and ends at same location"""
        return self.start_location_id == self.end_location_id
    
    @property
    def date(self) -> datetime:
        """Get route date (start date)"""
        return self.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class VehicleState:
    """Runtime state of a vehicle during simulation"""
    vehicle_id: int
    current_location_id: int
    current_odometer_km: int
    km_since_last_service: int
    km_driven_this_lease_year: int
    total_lifetime_km: int
    available_from: datetime
    last_route_id: Optional[int]
    lease_cycle_number: int
    lease_start_date: datetime
    lease_end_date: datetime
    annual_limit_km: int
    service_interval_km: int
    total_contract_limit_km: Optional[int]
    
    # Tracking
    relocations_in_window: List[Tuple[datetime, int, int]] = field(default_factory=list)
    total_relocations: int = 0
    total_relocation_cost: float = 0.0
    total_overage_cost: float = 0.0
    routes_completed: int = 0
    
    def can_swap_at(self, date: datetime, swap_period_days: int = 90) -> bool:
        """Check if vehicle can perform a swap at given date"""
        if not self.relocations_in_window:
            return True
        
        # Check if any relocation in the last swap_period_days
        cutoff = date - timedelta(days=swap_period_days)
        recent_relocations = [r for r in self.relocations_in_window if r[0] >= cutoff]
        
        return len(recent_relocations) == 0
    
    def add_relocation(self, date: datetime, from_loc: int, to_loc: int, cost: float):
        """Record a relocation"""
        self.relocations_in_window.append((date, from_loc, to_loc))
        self.total_relocations += 1
        self.total_relocation_cost += cost
    
    def needs_service(self, tolerance_km: int = 1000) -> bool:
        """Check if service is needed"""
        return self.km_since_last_service > (self.service_interval_km + tolerance_km)


@dataclass
class RouteAssignment:
    """Assignment of a vehicle to a route"""
    route_id: int
    vehicle_id: int
    date: datetime
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
    relocation_from: Optional[int] = None
    relocation_to: Optional[int] = None
    relocation_distance: float = 0.0
    relocation_time: float = 0.0
    overage_km: int = 0
    chain_score: float = 0.0  # For look-ahead scoring


@dataclass
class PlacementResult:
    """Result of placement algorithm"""
    placements: dict  # vehicle_id -> location_id
    demand_analysis: dict  # location_id -> route_count
    total_vehicles_placed: int
    locations_used: int
    avg_vehicles_per_location: float


@dataclass
class AssignmentResult:
    """Result of assignment algorithm"""
    assignments: List[RouteAssignment]
    vehicle_states: dict  # vehicle_id -> VehicleState
    total_cost: float
    total_relocation_cost: float
    total_overage_cost: float
    routes_assigned: int
    routes_unassigned: int
    avg_cost_per_route: float


@dataclass
class AssignmentConfig:
    """Configuration for assignment algorithm"""
    # Cost parameters
    relocation_base_cost_pln: float = 1000.0
    relocation_per_km_pln: float = 1.0
    relocation_per_hour_pln: float = 150.0
    overage_per_km_pln: float = 0.92
    
    # Service parameters
    service_tolerance_km: int = 1000
    service_duration_hours: int = 48
    service_penalty_pln: float = 500.0
    
    # Swap policy
    max_swaps_per_period: int = 1
    swap_period_days: int = 90
    
    # Look-ahead parameters
    look_ahead_days: int = 7
    chain_depth: int = 3  # How many routes ahead to consider
    
    # Placement parameters
    placement_lookahead_days: int = 14

