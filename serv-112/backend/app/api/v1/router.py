from fastapi import APIRouter
from app.api.v1 import (
    auth, scenarios, scenario_turns, sessions, admin, classifiers,
    incident_cards, users, action_traces, audit, settings, runtime,
)

router = APIRouter()
router.include_router(auth.router,            prefix="/auth",         tags=["auth"])
router.include_router(users.router,           prefix="/users",        tags=["users"])
router.include_router(scenarios.router,       prefix="/scenarios",    tags=["scenarios-legacy"])
router.include_router(scenario_turns.router,  prefix="/scenarios",    tags=["scenario-turns-legacy"])
router.include_router(incident_cards.router,  prefix="/cards",        tags=["incident-cards"])
router.include_router(action_traces.router,   prefix="/traces",       tags=["action-traces"])
router.include_router(sessions.router,        prefix="/sessions",     tags=["sessions"])
router.include_router(classifiers.router,     prefix="/classifiers",  tags=["classifiers"])
router.include_router(runtime.router,          prefix="/runtime",     tags=["runtime"])
router.include_router(audit.router,           prefix="/audit",        tags=["audit"])
router.include_router(settings.router,        prefix="/settings",     tags=["settings"])
router.include_router(admin.router,            prefix="/admin",        tags=["admin"])
