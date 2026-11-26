"""Versioned API router."""

from fastapi import APIRouter

from app.api.v1 import admin, auth, courses, demo, essays, evaluations, reviews, rubrics, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(admin.router)
router.include_router(courses.router)
router.include_router(essays.router)
router.include_router(rubrics.router)
router.include_router(evaluations.router)
router.include_router(reviews.router)
router.include_router(demo.router)
