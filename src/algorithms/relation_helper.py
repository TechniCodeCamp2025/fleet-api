"""
Relation lookup helper with caching and validation.
Reduces code duplication and provides consistent relation lookups.
"""
from typing import Dict, Optional, Tuple
from functools import lru_cache


def get_cached_relation(
    from_location: int,
    to_location: int,
    relation_lookup: Dict,
    config,
    relation_cache: Optional[Dict] = None
):
    """
    Get relation between two locations with caching support.
    
    This is the single source of truth for relation lookups.
    
    Args:
        from_location: Starting location ID
        to_location: Destination location ID
        relation_lookup: Dictionary of all relations
        config: Configuration object with use_relation_cache and use_pathfinding
        relation_cache: Optional cache dictionary (mutable, will be updated)
    
    Returns:
        LocationRelation object or None if no path exists
    """
    from data_loader import get_relation
    
    # Early return if same location
    if from_location == to_location:
        return None  # No relocation needed
    
    # Check cache first
    cache_key = (from_location, to_location)
    
    if relation_cache is not None and config.use_relation_cache:
        if cache_key in relation_cache:
            return relation_cache[cache_key]
    
    # Lookup relation
    relation = get_relation(
        from_location,
        to_location,
        relation_lookup,
        use_pathfinding=config.use_pathfinding
    )
    
    # Store in cache
    if relation_cache is not None and config.use_relation_cache:
        relation_cache[cache_key] = relation
    
    return relation


def calculate_relocation_cost(relation, config) -> float:
    """
    Calculate cost of a relocation based on relation.
    
    Args:
        relation: LocationRelation object
        config: Configuration with cost parameters
    
    Returns:
        Total relocation cost in PLN
    """
    if not relation:
        return 0.0
    
    cost = config.relocation_base_cost_pln
    cost += relation.dist * config.relocation_per_km_pln
    # relation.time is in minutes, convert to hours for cost calculation
    cost += (relation.time / 60.0) * config.relocation_per_hour_pln
    
    return cost


def get_relocation_info(
    from_location: int,
    to_location: int,
    relation_lookup: Dict,
    config,
    relation_cache: Optional[Dict] = None
) -> Tuple[Optional[object], float]:
    """
    Get relation and cost for a relocation in one call.
    
    Args:
        from_location: Starting location ID
        to_location: Destination location ID
        relation_lookup: Dictionary of all relations
        config: Configuration object
        relation_cache: Optional cache dictionary
    
    Returns:
        (relation, cost) tuple
        - relation: LocationRelation or None
        - cost: Relocation cost in PLN (0.0 if no relocation or no path)
    """
    relation = get_cached_relation(
        from_location, to_location, relation_lookup, config, relation_cache
    )
    
    if not relation:
        return None, 0.0
    
    cost = calculate_relocation_cost(relation, config)
    
    return relation, cost


class RelationCacheStats:
    """Statistics for relation cache performance."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.size = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def __str__(self):
        return (f"Cache: {self.size} entries, "
                f"{self.hit_rate:.1%} hit rate "
                f"({self.hits} hits, {self.misses} misses)")


def create_relation_cache(config, enable_stats: bool = False):
    """
    Create a relation cache with optional statistics tracking.
    
    Args:
        config: Configuration object
        enable_stats: Whether to track cache statistics
    
    Returns:
        Cache dictionary (empty dict if caching disabled, None if not used)
    """
    if not config.use_relation_cache:
        return None
    
    cache = {}
    
    if enable_stats:
        cache._stats = RelationCacheStats()
    
    return cache


def get_cache_stats(relation_cache: Optional[Dict]) -> Optional[RelationCacheStats]:
    """Get statistics from a relation cache if available."""
    if relation_cache is None:
        return None
    
    if hasattr(relation_cache, '_stats'):
        relation_cache._stats.size = len(relation_cache)
        return relation_cache._stats
    
    # Return basic stats without hit/miss tracking
    stats = RelationCacheStats()
    stats.size = len(relation_cache)
    return stats

