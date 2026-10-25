import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_test_database_is_accessible(db_session):
    result = await db_session.scalar(text("SELECT current_database()"))
    assert result == "aegis_test"