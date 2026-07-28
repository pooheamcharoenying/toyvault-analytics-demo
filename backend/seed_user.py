"""CLI to create/seed a ToyVault demo user. Requires Mongo configured
(MONGODB_URI, or MONGODB_USER_ME + MONGODB_PASSWORD_ME + MONGODB_HOST).

Run from the backend/ directory:
    python seed_user.py <username> <password> [--name "Display Name"] [--role user|admin]

Examples:
    python seed_user.py admin 'ChangeMe!2026' --name "Demo Admin" --role admin
    python seed_user.py demo  'demo1234'      --name "Demo Viewer" --role user

(Lives at backend/ root, not backend/scripts/, because `scripts/` is gitignored
in this public repo.)
"""
import argparse
import os
import sys

# make `import app...` work regardless of the current working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Create or update a ToyVault user.")
    ap.add_argument("username")
    ap.add_argument("password")
    ap.add_argument("--name", default=None, help="display name")
    ap.add_argument("--role", default="user", choices=["user", "admin"])
    args = ap.parse_args()

    from app.utils import mongo_store as ms
    if not ms.is_enabled():
        print("ERROR: Mongo not configured. Set MONGODB_URI (or MONGODB_USER_ME + "
              "MONGODB_PASSWORD_ME + MONGODB_HOST) in backend/.env before seeding users.")
        return 1

    from app.auth import store
    try:
        uname = store.create_user(args.username, args.password, args.name, args.role)
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"OK: user '{uname}' (role={args.role}) created/updated in db '{ms.get_db_name()}' "
          f"[{ms.describe_credential_source()}].")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
