"""
Path-finding for multi-hop routes between locations.
"""
from typing import Dict, List, Tuple, Optional
import heapq
from dataclasses import dataclass


@dataclass
class PathResult:
    """Result of pathfinding"""
    exists: bool
    distance_km: float
    time_hours: float
    path: List[int]  # List of location IDs


def find_shortest_path(
    from_loc: int,
    to_loc: int,
    relation_lookup: Dict,
    all_locations: set = None,
    max_hops: int = 3
) -> PathResult:
    """
    Find shortest path between two locations using Dijkstra's algorithm.
    Limited to max_hops to prevent excessive computation.
    
    Args:
        from_loc: Starting location ID
        to_loc: Destination location ID
        relation_lookup: Dict of (loc1, loc2) -> LocationRelation
        all_locations: Set of all valid location IDs (optional, inferred if not provided)
        max_hops: Maximum number of hops allowed (default: 3)
    
    Returns:
        PathResult with path details
    """
    # Same location
    if from_loc == to_loc:
        return PathResult(True, 0.0, 0.0, [from_loc])
    
    # Try direct connection first
    direct = relation_lookup.get((from_loc, to_loc))
    if direct:
        # Convert time from minutes to hours for PathResult
        return PathResult(True, direct.dist, direct.time / 60.0, [from_loc, to_loc])
    
    # Try reverse
    direct_rev = relation_lookup.get((to_loc, from_loc))
    if direct_rev:
        # Convert time from minutes to hours for PathResult
        return PathResult(True, direct_rev.dist, direct_rev.time / 60.0, [from_loc, to_loc])
    
    # Build adjacency graph if we need multi-hop
    if all_locations is None:
        # Infer locations from relations
        all_locations = set()
        for (loc1, loc2) in relation_lookup.keys():
            all_locations.add(loc1)
            all_locations.add(loc2)
    
    # Build adjacency list
    adjacency = {}
    for (loc1, loc2), relation in relation_lookup.items():
        if loc1 not in adjacency:
            adjacency[loc1] = []
        # Convert time from minutes to hours for pathfinding
        adjacency[loc1].append((loc2, relation.dist, relation.time / 60.0))
        
        # Assume bidirectional
        if loc2 not in adjacency:
            adjacency[loc2] = []
        # Convert time from minutes to hours for pathfinding
        adjacency[loc2].append((loc1, relation.dist, relation.time / 60.0))
    
    # Dijkstra's algorithm with hop limit
    # Priority queue: (total_time, current_loc, total_dist, path, hops)
    pq = [(0.0, 0.0, from_loc, [from_loc], 0)]
    visited = set()
    
    while pq:
        total_time, total_dist, current, path, hops = heapq.heappop(pq)
        
        if current in visited:
            continue
        
        visited.add(current)
        
        if current == to_loc:
            return PathResult(True, total_dist, total_time, path)
        
        # Stop if we've reached max hops
        if hops >= max_hops:
            continue
        
        if current not in adjacency:
            continue
        
        for neighbor, edge_dist, edge_time in adjacency[current]:
            if neighbor not in visited:
                new_time = total_time + edge_time
                new_dist = total_dist + edge_dist
                new_path = path + [neighbor]
                new_hops = hops + 1
                heapq.heappush(pq, (new_time, new_dist, neighbor, new_path, new_hops))
    
    # No path found within hop limit
    return PathResult(False, float('inf'), float('inf'), [])


# Cache for path results to avoid recomputing
_path_cache: Dict[Tuple[int, int], PathResult] = {}


def get_path_with_cache(
    from_loc: int,
    to_loc: int,
    relation_lookup: Dict,
    all_locations: set = None
) -> PathResult:
    """Get path with caching for performance"""
    cache_key = (from_loc, to_loc)
    
    if cache_key not in _path_cache:
        _path_cache[cache_key] = find_shortest_path(from_loc, to_loc, relation_lookup, all_locations)
    
    return _path_cache[cache_key]


def clear_path_cache():
    """Clear the path cache"""
    global _path_cache
    _path_cache = {}

