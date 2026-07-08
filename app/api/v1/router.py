"""Aggregates all v1 route modules into a single router.

As later phases land, register additional routers here (verify,
verifications, reviews, reports, subscriptions, admin).
"""

from fastapi import APIRouter

from app.api.v1.routes import (
    account,
    health,
    reviews,
    verifications,
    verify,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(account.router)
api_router.include_router(verify.router)
api_router.include_router(reviews.router)
api_router.include_router(verifications.router)
