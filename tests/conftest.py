from os import mkdir
from pytest import fixture
from shutil import rmtree

from .constants import (
    OPERANDI_SERVER_BASE_DIR,
    OPERANDI_TESTS_LOCAL_DIR_WORKFLOW_JOBS,
    OPERANDI_TESTS_LOCAL_DIR_WORKFLOWS,
    OPERANDI_TESTS_LOCAL_DIR_WORKSPACES
)

pytest_plugins = [
    "tests.fixtures.authentication",
    "tests.fixtures.database",
    "tests.fixtures.workflow",
    "tests.fixtures.workspace"
]


@fixture(scope="session", autouse=True)
def do_before_all_tests():
    rmtree(OPERANDI_SERVER_BASE_DIR, ignore_errors=True)
    mkdir(mode=0o777, path=OPERANDI_SERVER_BASE_DIR)
    mkdir(mode=0o777, path=OPERANDI_TESTS_LOCAL_DIR_WORKFLOW_JOBS)
    mkdir(mode=0o777, path=OPERANDI_TESTS_LOCAL_DIR_WORKFLOWS)
    mkdir(mode=0o777, path=OPERANDI_TESTS_LOCAL_DIR_WORKSPACES)
