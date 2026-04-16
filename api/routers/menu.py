from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from scrapers.menu import scrape_menu_data
from utils.cache_manager import cache_manager
import asyncio
from typing import Optional

router = APIRouter()

async def get_scraped_menu(locale: str = 'el'):
    """Get menu data, using cache if available and fresh."""
    now = datetime.now()
    
    # Try to get from cache
    cached_item = cache_manager.get_cached_item('menu', locale)
    
    if cached_item:
        data, timestamp = cached_item
        # Check if cache is still fresh (less than 1 day old)
        if now - timestamp < timedelta(days=1):
            return data
    
    # Cache miss or stale - scrape new data
    fresh_data = await scrape_menu_data(locale)
    cache_manager.set_cached_item('menu', locale, fresh_data, now)
    
    return fresh_data

async def scrape_all_locales():
    # Assuming 'el' and 'en' are the only locales for now
    await get_scraped_menu('el')
    await get_scraped_menu('en')

async def schedule_daily_scraping():
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await scrape_all_locales()


@router.get("/menu")
async def get_menu_endpoint(locale: Optional[str] = Query('el', enum=['el', 'en'])):
    menu_data = await get_scraped_menu(locale)

    # Check if any day's menu date matches today
    today_str = datetime.now().strftime('%d/%m/%Y')
    club_open = False
    days = menu_data.get('days', [])

    import re
    date_regex = re.compile(r'(?:📅\s*)?(\d{1,2}/\d{1,2}/\d{4})')
    for day in days:
        # Extract date from the HTML (menu-date)
        full_html = day.get('full', '')
        match = date_regex.search(full_html)
        if match and match.group(1) == today_str:
            club_open = True
            break

    return {"menu": menu_data, "club_open": club_open}
