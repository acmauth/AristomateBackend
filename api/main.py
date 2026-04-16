from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from routers import menu_router, map_router
from routers.menu import scrape_all_locales, schedule_daily_scraping


@asynccontextmanager
async def lifespan(app: FastAPI):
    await scrape_all_locales()
    asyncio.create_task(schedule_daily_scraping())
    yield

app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menu_router)
app.include_router(map_router)