# Backend Coding Standards


## 1. Project Structure
- Organize code by feature/domain, not by technical layer (avoid a single
  giant `utils.py` or `helpers.py`).
- One class or tightly related group of functions per file.
- Keep business logic separate from framework/routing code (e.g. controllers
  should be thin; logic lives in service/repository layers).

## 2. Naming Conventions
- `snake_case` for functions, variables, and file names.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for constants.
- Names should describe intent, not implementation (`get_active_users`, not
  `get_users_where_flag_true`).

## 3. Error Handling
- Never use bare `except:` - catch specific exceptions.
- Raise custom exception classes for domain errors instead of returning
  `None`/error codes silently.
- Log errors with enough context (request id, user id, input parameters) to
  debug without reproducing locally.

## 4. Logging
- Use the standard `logging` module (or the team's configured logger), never
  bare `print()` statements in production code.
- Log at the appropriate level: `DEBUG` for development detail, `INFO` for
  normal operation events, `WARNING`/`ERROR` for problems.

## 5. API Design
- REST endpoints follow `/api/v1/<resource>` pluralized naming.
- Return consistent JSON error shapes: `{"error": {"code": ..., "message": ...}}`.
- Validate all input at the boundary (request schema validation) before it
  reaches business logic.

## 6. Testing
- Every new function with business logic needs at least one unit test.
- Use `pytest`. Test files mirror source structure: `src/foo.py` ->
  `tests/test_foo.py`.
- Mock external calls (DB, third-party APIs) in unit tests; integration
  tests are separate and clearly marked.

## 7. Documentation
- Every public function/class gets a docstring describing purpose,
  parameters, and return value.
- Non-obvious business logic gets an inline comment explaining *why*, not
  *what*.

## 8. Security
- Never hardcode credentials, tokens, or connection strings - use
  environment variables / secrets manager.
- Sanitize and parameterize all database queries (no string-concatenated
  SQL).
