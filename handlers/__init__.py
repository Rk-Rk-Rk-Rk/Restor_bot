from aiogram import Router

from .registration import router as reg_router
from .booking import router as booking_router
from .menu_order import router as menu_router
from .profile import router as profile_router
from .admin import router as admin_router


def get_all_routers() -> list[Router]:
    return [reg_router, booking_router, menu_router, profile_router, admin_router]
