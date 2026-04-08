from sqlalchemy import String

from src.users.models import User


def test_username_column_has_no_length_limit():
    col = User.__table__.columns["username"]
    assert isinstance(col.type, String)
    assert col.type.length is None
