"""CLI commands for managing the application."""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from src.database import SessionLocal, engine, Base
from src.services.user_service import UserExistsError, UserService
from src.repositories.user_repository import UserRepository
from src.repositories.invitation_repository import InvitationRepository


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def create_admin(email: str, password: str | None = None, display_name: str | None = None) -> None:
    """Create an admin user.

    Args:
        email: Admin's email address.
        password: Admin's password. If not provided, prompts for input.
        display_name: Admin's display name. Defaults to email username.
    """
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    if password is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: Passwords do not match.")
            sys.exit(1)

    if not password or len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    db = get_db()
    try:
        user_repo = UserRepository(db)
        invitation_repo = InvitationRepository(db)
        user_service = UserService(user_repo, invitation_repo)

        user = user_service.create_admin(
            email=email,
            password=password,
            display_name=display_name,
        )

        print(f"Admin user created successfully!")
        print(f"  ID: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Display Name: {user.display_name}")
        print(f"  Role: {user.role}")

    except UserExistsError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating admin user: {e}")
        sys.exit(1)
    finally:
        db.close()


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="YouTube Transcript API management commands"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-admin command
    create_admin_parser = subparsers.add_parser(
        "create-admin",
        help="Create an admin user"
    )
    create_admin_parser.add_argument(
        "--email",
        required=True,
        help="Admin email address"
    )
    create_admin_parser.add_argument(
        "--display-name",
        help="Admin display name (defaults to email username)"
    )

    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin(
            email=args.email,
            display_name=args.display_name,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
