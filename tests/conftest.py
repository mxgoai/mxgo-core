from unittest.mock import patch

import pytest

import mxtoai.db


@pytest.fixture(autouse=True, scope="session")
def patch_db_uri_from_env():
    with patch.object(mxtoai.db.DbConnection, "get_db_uri_from_env", return_value=""), \
         patch.object(mxtoai.db.AsyncDbConnection, "get_db_uri_from_env", return_value=""):
        yield
