"""Канонические строковые идентификаторы действий аудита."""


class AuditAction:
    # --- auth -------------------------------------------------------------
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_BLOCKED = "login_blocked"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REFRESH_FAILED = "token_refresh_failed"
    PASSWORD_RESET = "password_reset"

    # --- users ------------------------------------------------------------
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"

    # --- scenarios / turns ------------------------------------------------
    SCENARIO_CREATED = "scenario_created"
    SCENARIO_UPDATED = "scenario_updated"
    SCENARIO_DEACTIVATED = "scenario_deactivated"
    TURN_CREATED = "turn_created"
    TURN_UPDATED = "turn_updated"
    TURN_DELETED = "turn_deleted"
    TURN_REORDERED = "turn_reordered"

    # --- cards / traces ---------------------------------------------------
    CARD_CREATED = "card_created"
    CARD_UPDATED = "card_updated"
    CARD_DELETED = "card_deleted"
    TRACE_CREATED = "trace_created"
    TRACE_UPDATED = "trace_updated"
    TRACE_DELETED = "trace_deleted"

    # --- system -----------------------------------------------------------
    APP_STARTED = "app_started"
    APP_STOPPED = "app_stopped"
    AUDIT_CLEANUP = "audit_cleanup"
    SETTINGS_UPDATED = "settings_updated"
    UNHANDLED_EXCEPTION = "unhandled_exception"

    # --- security ---------------------------------------------------------
    ACCESS_DENIED = "access_denied"
    INVALID_TOKEN = "invalid_token"
    SELF_DEACTIVATE_BLOCKED = "self_deactivate_blocked"

    # --- admin restrictions -----------------------------------
    ADMIN_ACTION_BLOCKED = "admin_action_blocked"

    # --- backups ----------------------------------------------------------
    BACKUP_CREATED = "backup_created"
    BACKUP_FAILED = "backup_failed"
    BACKUP_RESTORED = "backup_restored"
    BACKUP_DELETED = "backup_deleted"