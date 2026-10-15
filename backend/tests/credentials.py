"""Passwords and identities for test users, generated fresh on every run so none are hardcoded in the repo."""
import secrets

PASSWORD = secrets.token_urlsafe(16)        # the password every test user is registered with
OTHER_PASSWORD = secrets.token_urlsafe(16)  # a second valid password (e.g. the new one in a password change)
WRONG_PASSWORD = secrets.token_urlsafe(16)  # never set on any account

_issued = set()


def _name() -> str:
    """A random, run-unique username such as 'user_3fa91c07'."""
    while (name := "user_" + secrets.token_hex(4)) in _issued:
        pass
    _issued.add(name)
    return name


USERNAME = _name()        # the user of the auth_headers fixture
OTHER_USERNAME = _name()  # a second user, always different from USERNAME

EMAIL = f"{USERNAME}@example.com"
OTHER_EMAIL = f"{OTHER_USERNAME}@example.com"
