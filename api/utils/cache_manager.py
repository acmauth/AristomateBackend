"""
Centralized cache management for the API.
Handles caching of various data types including menu data, and can be extended for other scrapers.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Dict


class CacheManager:
    """Manages persistent cache storage for various data types."""
    
    def __init__(self, cache_dir: Path = None):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory to store cache files. Defaults to 'data' directory.
        """
        if cache_dir is None:
            # Use data directory at the root of the API project
            cache_dir = Path(__file__).parent.parent / 'data'
        
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        
    def _get_cache_file(self, cache_type: str) -> Path:
        """Get the cache file path for a specific cache type."""
        return self.cache_dir / f"{cache_type}_cache.json"
    
    def load_cache(self, cache_type: str) -> Dict[str, Any]:
        """
        Load cache data for a specific type.
        
        Args:
            cache_type: Type of cache to load (e.g., 'menu', 'gym', 'metro')
            
        Returns:
            Dictionary containing cached data with structure:
            {
                'locale_or_key': {
                    'data': <cached_data>,
                    'timestamp': <iso_timestamp>
                }
            }
        """
        cache_file = self._get_cache_file(cache_type)
        
        if not cache_file.exists():
            return {}
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading cache for {cache_type}: {e}")
            return {}
    
    def save_cache(self, cache_type: str, data: Dict[str, Any]):
        """
        Save cache data for a specific type.
        
        Args:
            cache_type: Type of cache to save (e.g., 'menu', 'gym', 'metro')
            data: Dictionary to save with the expected structure
        """
        cache_file = self._get_cache_file(cache_type)
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving cache for {cache_type}: {e}")
    
    def get_cached_item(self, cache_type: str, key: str) -> Optional[tuple[Any, datetime]]:
        """
        Get a specific cached item.
        
        Args:
            cache_type: Type of cache
            key: Cache key (e.g., locale for menu)
            
        Returns:
            Tuple of (data, timestamp) if found, None otherwise
        """
        cache = self.load_cache(cache_type)
        item = cache.get(key)
        
        if not item:
            return None
        
        data = item.get('data')
        timestamp_str = item.get('timestamp')
        
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
            return (data, timestamp)
        
        return None
    
    def set_cached_item(self, cache_type: str, key: str, data: Any, timestamp: datetime = None):
        """
        Set a specific cached item.
        
        Args:
            cache_type: Type of cache
            key: Cache key (e.g., locale for menu)
            data: Data to cache
            timestamp: Timestamp for the cache entry (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        cache = self.load_cache(cache_type)
        
        cache[key] = {
            'data': data,
            'timestamp': timestamp.isoformat()
        }
        
        self.save_cache(cache_type, cache)
    
    def clear_cache(self, cache_type: str, key: Optional[str] = None):
        """
        Clear cache data.
        
        Args:
            cache_type: Type of cache to clear
            key: Specific key to clear, or None to clear all
        """
        if key is None:
            # Clear entire cache type
            cache_file = self._get_cache_file(cache_type)
            if cache_file.exists():
                cache_file.unlink()
        else:
            # Clear specific key
            cache = self.load_cache(cache_type)
            if key in cache:
                del cache[key]
                self.save_cache(cache_type, cache)


# Global cache manager instance
cache_manager = CacheManager()
