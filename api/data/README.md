# API Cache System

## Overview
The API uses a centralized cache management system that stores cached data persistently in the `data/` directory.

## Structure
```
data/
├── .gitignore          # Ignores cache files from git
├── .gitkeep            # Keeps directory in git
├── menu_cache.json     # Menu data cache
└── <type>_cache.json   # Future cache files (gym, metro, etc.)
```

## Cache File Format
Each cache file follows this structure:
```json
{
  "key": {
    "data": <cached_data>,
    "timestamp": "2025-10-25T21:21:54.497787"
  }
}
```

For menu cache, the key is the locale (e.g., "el", "en").

## Persistence
- Cache files are stored in `data/` directory
- This directory is mounted as a volume in Docker to persist data
- Cache survives container restarts and rebuilds
- Cache is excluded from git but the directory structure is preserved

## Adding New Cache Types
To add caching for a new scraper:

```python
from cache_manager import cache_manager

# Save data
cache_manager.set_cached_item('gym', 'auth', gym_data)

# Load data
cached = cache_manager.get_cached_item('gym', 'auth')
if cached:
    data, timestamp = cached
    # Check if fresh and use data

# Clear cache
cache_manager.clear_cache('gym', 'auth')  # Clear specific key
cache_manager.clear_cache('gym')          # Clear all gym cache
```

## Cache Invalidation
- Menu cache: 24 hours
- Custom TTL can be implemented per cache type in the router logic
