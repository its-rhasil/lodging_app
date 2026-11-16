"""Operator commands (DL-R03, DL-R04). Run from the project root:

    venv\\Scripts\\python.exe -m app.cli create-superadmin --email ops@example.com --name "Ops"
    venv\\Scripts\\python.exe -m app.cli create-tenant --name "Sea View Lodge" \\
        --contact-email desk@seaview.in --contact-phone 9000000000 \\
        --admin-email owner@seaview.in --admin-name "Owner"

Passwords are never command-line arguments (they'd land in shell history). They come
from an environment variable (SUPERADMIN_PASSWORD / TENANT_ADMIN_PASSWORD), or the
command asks for them twice without echoing.
"""
import argparse
import getpass as getpass_module
import os
import sys
from collections.abc import Callable, Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import CONSTRAINT_ERRORS, DomainError


def _password(env_var: str, environ: Mapping[str, str], getpass: Callable[[str], str]) -> str:
    if environ.get(env_var):
        return environ[env_var]
    first = getpass("Password: ")
    if getpass("Repeat password: ") != first:
        raise DomainError("Passwords don't match.", code="password_mismatch")
    return first


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    superadmin = commands.add_parser("create-superadmin", help="Create a platform superadmin")
    superadmin.add_argument("--email", help="defaults to $SUPERADMIN_EMAIL")
    superadmin.add_argument("--name", required=True)

    tenant = commands.add_parser("create-tenant", help="Create a tenant and its tenant admin")
    tenant.add_argument("--name", required=True)
    tenant.add_argument("--contact-email", required=True)
    tenant.add_argument("--contact-phone", required=True)
    tenant.add_argument("--address")
    tenant.add_argument("--admin-email", required=True)
    tenant.add_argument("--admin-name", required=True)
    return parser


def main(argv: list[str] | None = None, *, db: Session | None = None,
         environ: Mapping[str, str] = os.environ,
         getpass: Callable[[str], str] = getpass_module.getpass) -> int:
    """Returns the exit code. Tests pass their own db, environ and getpass."""
    from app.service import platform_service, tenant_service

    args = _parser().parse_args(argv)
    own_session = db is None
    if own_session:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        if args.command == "create-superadmin":
            email = args.email or environ.get("SUPERADMIN_EMAIL")
            if not email:
                raise DomainError("Give --email or set SUPERADMIN_EMAIL.", code="field_required")
            password = _password("SUPERADMIN_PASSWORD", environ, getpass)
            user = platform_service.create_superadmin(db, email=email, name=args.name, password=password)
            print(f"Created superadmin {user.email} (id {user.id}).")
        else:
            password = _password("TENANT_ADMIN_PASSWORD", environ, getpass)
            tenant, admin = tenant_service.create_tenant(
                db, name=args.name, contact_email=args.contact_email, contact_phone=args.contact_phone,
                address=args.address, admin_email=args.admin_email, admin_name=args.admin_name,
                admin_password=password,
            )
            print(f"Created tenant {tenant.name!r} (id {tenant.id}) with tenant admin {admin.email} (id {admin.id}).")
        return 0
    except DomainError as exc:
        db.rollback()
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except IntegrityError as exc:
        db.rollback()
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        _, message = CONSTRAINT_ERRORS.get(name, ("conflict", "That conflicts with existing data."))
        print(f"Error: {message}", file=sys.stderr)
        return 1
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
