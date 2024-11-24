import os
import shutil

import pytest
from measure.const import PROJECT_DIR


@pytest.fixture(autouse=True)
def clean_export_directory() -> None:
    export_dir = os.path.join(PROJECT_DIR, "export")
    shutil.rmtree(export_dir)
    yield
