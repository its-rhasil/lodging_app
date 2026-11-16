"""Permission catalogue and default role mapping (architecture.md §6.3, DL-P18).

The database rows (roles, permissions, role_permissions) are seeded by the
baseline migration with these exact values. The test suite seeds from here.
If you change this file, the DB needs a data migration too.
"""

ROLES: dict[str, tuple[str, str]] = {
    "tenant_admin": ("Tenant admin", "All permissions in the tenant; exactly one per tenant."),
    "manager": ("Manager", "Front desk plus money exceptions and forced checkout."),
    "receptionist": ("Receptionist", "Front desk operations."),
}

PERMISSIONS: dict[str, str] = {
    "dashboard.view": "View the dashboard",
    "room.view": "View rooms",
    "room.status.update": "Change a room's operational status",
    "inventory.manage": "Manage stay plans, room types, rates and rooms",
    "guest.view": "View and search guests",
    "stay.view": "View stays",
    "stay.check_in": "Check a guest in",
    "stay.check_out": "Check a guest out",
    "stay.extend": "Extend a stay",
    "stay.change_room": "Move a stay to another room",
    "stay.convert_to_daily": "Convert a fresh-up or hourly stay to full day",
    "stay.override_rate": "Check in at a non-default (bargained) rate",
    "stay.backdate": "Backdate a check-in beyond the allowed window",
    "folio.view": "View folios and balances",
    "folio.post_charge": "Post service and restaurant charges",
    "payment.record": "Record a payment",
    "payment.refund": "Record a refund",
    "folio.waive": "Waive (part of) a charge",
    "folio.reverse": "Reverse a folio transaction",
    "folio.close_with_balance": "Check out with a balance owed",
    "user.manage": "Create and deactivate users, assign roles, set overrides",
    "audit.view": "View the audit trail",
    "settings.manage": "Manage tenant settings",
}

_RECEPTIONIST = {
    "dashboard.view", "room.view", "room.status.update", "guest.view",
    "stay.view", "stay.check_in", "stay.check_out", "stay.extend", "stay.change_room",
    "stay.convert_to_daily", "stay.override_rate",
    "folio.view", "folio.post_charge", "payment.record", "folio.waive",
}
_MANAGER = _RECEPTIONIST | {
    "stay.backdate", "payment.refund", "folio.reverse", "folio.close_with_balance",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "receptionist": frozenset(_RECEPTIONIST),
    "manager": frozenset(_MANAGER),
    "tenant_admin": frozenset(PERMISSIONS),
}
