"""Report actionable errors without exposing credentials or SQL parameters."""
import sys
from sqlalchemy.exc import SQLAlchemyError

def run(main):
    try:
        main()
    except SQLAlchemyError as exc:
        original = getattr(exc, 'orig', None)
        args = getattr(original, 'args', ())
        code = args[0] if args and isinstance(args[0], int) else 'unknown'
        print(f'[ERROR] MySQL {type(exc).__name__}, code={code}. Check Docker health, .env connection settings, schema and permissions.', file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        sys.exit(1)
