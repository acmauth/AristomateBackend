from fastapi import APIRouter, Query
import os
import time
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote
import requests
from dotenv import load_dotenv

router = APIRouter()

load_dotenv()

USERNAME = os.getenv('GIS_USERNAME')
PASSWORD = os.getenv('GIS_PASSWORD')

# Token cache
_token_cache = {
    'token': None,
    'expires': 0
}

# Buildings cache (24 hour lifetime)
_buildings_cache = {
    'data': None,
    'expires': 0
}

BUILDINGS_CACHE_LIFETIME = 24 * 60 * 60 * 1000  # 24 hours in milliseconds


def _generate_initial_token():
    """Generate initial token using username/password"""
    data = f'request=getToken&username={quote(USERNAME)}&password={quote(PASSWORD)}&expiration=60&referer=https%3A%2F%2Fgeoportal.auth.gr&f=json'
    headers = {
        'accept': '*/*',
        'accept-language': 'en-GB,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://geoportal.auth.gr',
        'referer': 'https://geoportal.auth.gr/giswa/rest/services/Aristomate/InteriorSpace_001_026/MapServer?f=jsapi',
        'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"'
    }
    response = requests.post('https://geoportal.auth.gr/main/sharing/rest/generateToken', headers=headers, data=data, verify=True)
    return response.json()


def _get_token(token):
    """Get token using existing token"""
    data = f'request=getToken&serverUrl=https%3A%2F%2Fgeoportal.auth.gr%2Fgiswa%2Frest%2Fservices%2FAristomate%2FInteriorSpace_001_026%2FMapServer&token={quote(token)}&referer=https%3A%2F%2Fgeoportal.auth.gr&f=json'
    headers = {
        'accept': '*/*',
        'accept-language': 'en-GB,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'dnt': '1',
        'origin': 'https://geoportal.auth.gr',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://geoportal.auth.gr/giswa/rest/services/Aristomate/InteriorSpace_001_026/MapServer?f=jsapi',
        'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    }
    response = requests.post('https://geoportal.auth.gr/main/sharing/rest/generateToken', headers=headers, data=data, verify=True)
    return response.json()


def get_valid_token():
    """Get a valid token, refreshing if necessary"""
    global _token_cache
    
    current_time = int(time.time() * 1000)  # Current time in milliseconds
    # Refresh token if it's expired or will expire in the next 5 minutes (300000ms)
    buffer_time = 300000
    
    if _token_cache['token'] is None or current_time >= (_token_cache['expires'] - buffer_time):
        # Generate new token
        initial_response = _generate_initial_token()
        if 'token' in initial_response:
            initial_token = initial_response['token']
            # Get the final token using the new format
            final_response = _get_token(initial_token)
            if 'token' in final_response:
                _token_cache['token'] = final_response['token']
                _token_cache['expires'] = final_response['expires']
    
    return _token_cache

@router.get("/get_gis_token")
async def getToken():
    """Proxy a request - returns a valid GIS token"""
    token_data = get_valid_token()
    return {
        "token": token_data['token'],
        "expires": token_data['expires']
    }

@router.get("/get_detailed_buildings")
async def get_detailed_buildings():
    global _buildings_cache
    
    current_time = int(time.time() * 1000)
    
    # Return cached data if still valid
    if _buildings_cache['data'] is not None and current_time < _buildings_cache['expires']:
        return _buildings_cache['data']
    
    BASEURL = "https://ws-ext.it.auth.gr"

    def getBuildings():
        response = requests.get(f"{BASEURL}/getBuildings2", verify=True)
        if not response.status_code == 200:
            return {"error": "Failed to fetch detailed buildings"}
        print(response.json())
        buildings = list(filter(lambda b: b.get('authBldId') is not None and b.get('gisBldId') is not None, response.json().get('buildings', [])))
        buildings = {b['authBldId']: b for b in buildings}
        return buildings
    
    async def getRooms(buildingID):
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(f"{BASEURL}/getRooms2/{buildingID}", verify=True))
        if response.status_code != 200:
            return []
        rooms = response.json().get('rooms', [])
        # Filter rooms that have roomCode, roomName, and roomId
        return [r for r in rooms if r.get('roomCode') and r.get('roomName') and r.get('roomId')]

    async def fetchRoomsForBuildings(buildingIds):
        """Fetch rooms for all buildings in parallel"""
        async def fetch_single(bld_id):
            rooms = await getRooms(bld_id)
            return (bld_id, rooms)
        
        entries = await asyncio.gather(*[fetch_single(bld_id) for bld_id in buildingIds])
        return dict(entries)

    buildings = getBuildings()
    if "error" in buildings:
        return buildings
    
    rooms_by_building = await fetchRoomsForBuildings(buildings.keys())
    
    returned_buildings = {}
    for bld_id, rooms in rooms_by_building.items():
        returned_buildings[bld_id] = rooms
    
    # Cache the result
    _buildings_cache['data'] = returned_buildings
    _buildings_cache['expires'] = current_time + BUILDINGS_CACHE_LIFETIME
    
    return returned_buildings