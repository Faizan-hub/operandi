from dotenv import load_dotenv
from os import environ
from os.path import join

__all__ = [
    "OPERANDI_DB_NAME",
    "OPERANDI_DB_URL",

    "OPERANDI_HARVESTER_DEFAULT_PASSWORD",
    "OPERANDI_HARVESTER_DEFAULT_USERNAME",

    "OPERANDI_HPC_DIR_HOME_SCRATCH",
    "OPERANDI_HPC_DIR_HOME_USER",
    "OPERANDI_HPC_DIR_PROJECT",
    "OPERANDI_HPC_HOST",
    "OPERANDI_HPC_HOST_PROXY",
    "OPERANDI_HPC_HOST_TRANSFER",
    "OPERANDI_HPC_HOST_TRANSFER_PROXY",
    "OPERANDI_HPC_SSH_KEYPATH",
    "OPERANDI_HPC_USERNAME",

    "OPERANDI_RABBITMQ_URL",
    "OPERANDI_RABBITMQ_EXCHANGE_NAME",
    "OPERANDI_RABBITMQ_EXCHANGE_ROUTER",
    "OPERANDI_RABBITMQ_QUEUE_DEFAULT",
    "OPERANDI_RABBITMQ_QUEUE_HARVESTER",
    "OPERANDI_RABBITMQ_QUEUE_USERS",

    "OPERANDI_LOGS_DIR",
    "OPERANDI_SERVER_BASE_DIR",
    "OPERANDI_SERVER_DEFAULT_PASSWORD",
    "OPERANDI_SERVER_DEFAULT_USERNAME",
    "OPERANDI_SERVER_URL_LIVE",
    "OPERANDI_SERVER_URL_LOCAL",

    "OPERANDI_TESTS_LOCAL_DIR_WORKFLOW_JOBS",
    "OPERANDI_TESTS_LOCAL_DIR_WORKFLOWS",
    "OPERANDI_TESTS_LOCAL_DIR_WORKSPACES",
    "OPERANDI_TESTS_HPC_DIR_BATCH_SCRIPTS",
    "OPERANDI_TESTS_HPC_DIR_SLURM_WORKSPACES"
]

load_dotenv()

OPERANDI_DB_NAME = environ.get("OPERANDI_DB_NAME", "operandi_db_tests")
OPERANDI_DB_URL = environ.get("OPERANDI_DB_URL")

OPERANDI_HARVESTER_DEFAULT_USERNAME: str = environ.get("OPERANDI_HARVESTER_DEFAULT_USERNAME")
OPERANDI_HARVESTER_DEFAULT_PASSWORD: str = environ.get("OPERANDI_HARVESTER_DEFAULT_PASSWORD")

OPERANDI_HPC_HOST: str = environ.get("OPERANDI_HPC_HOST", "login-mdc.hpc.gwdg.de")
OPERANDI_HPC_HOST_PROXY: str = environ.get("OPERANDI_HPC_HOST_PROXY", "login.gwdg.de")
OPERANDI_HPC_HOST_TRANSFER: str = environ.get("OPERANDI_HPC_HOST_TRANSFER", "transfer-scc.gwdg.de")
OPERANDI_HPC_HOST_TRANSFER_PROXY: str = environ.get("OPERANDI_HPC_HOST_TRANSFER_PROXY", "login.gwdg.de")
OPERANDI_HPC_SSH_KEYPATH: str = environ.get("OPERANDI_HPC_SSH_KEYPATH")
OPERANDI_HPC_USERNAME: str = environ.get("OPERANDI_HPC_USERNAME", "mmustaf")
OPERANDI_HPC_DIR_HOME_USER: str = environ.get(
    "OPERANDI_HPC_DIR_HOME_USER",
    f"/home/users/{OPERANDI_HPC_USERNAME}"
)
OPERANDI_HPC_DIR_HOME_SCRATCH: str = environ.get(
    "OPERANDI_HPC_DIR_HOME_SCRATCH",
    f"/scratch1/users/{OPERANDI_HPC_USERNAME}"
)
OPERANDI_HPC_PROJECT_NAME: str = environ.get(
    "OPERANDI_HPC_PROJECT_NAME",
    "operandi_tests"
)
OPERANDI_HPC_DIR_PROJECT: str = environ.get(
    "OPERANDI_HPC_DIR_PROJECT",
    f"{OPERANDI_HPC_DIR_HOME_SCRATCH}/{OPERANDI_HPC_PROJECT_NAME}"
)

OPERANDI_RABBITMQ_URL = environ.get("OPERANDI_RABBITMQ_URL")
OPERANDI_RABBITMQ_EXCHANGE_NAME = environ.get("OPERANDI_RABBITMQ_EXCHANGE_NAME", "operandi_default")
OPERANDI_RABBITMQ_EXCHANGE_ROUTER = environ.get("OPERANDI_RABBITMQ_EXCHANGE_ROUTER", "operandi_default_queue")
OPERANDI_RABBITMQ_QUEUE_DEFAULT = environ.get("OPERANDI_RABBITMQ_QUEUE_DEFAULT", "operandi_default_queue")
OPERANDI_RABBITMQ_QUEUE_HARVESTER = environ.get("OPERANDI_RABBITMQ_QUEUE_HARVESTER", "operandi_queue_harvester")
OPERANDI_RABBITMQ_QUEUE_USERS = environ.get("OPERANDI_RABBITMQ_QUEUE_USERS", "operandi_queue_users")

OPERANDI_LOGS_DIR: str = environ.get("OPERANDI_LOGS_DIR", "/tmp/operandi_logs_tests")
OPERANDI_SERVER_BASE_DIR = environ.get("OPERANDI_SERVER_BASE_DIR", "/tmp/operandi_data_tests")
OPERANDI_SERVER_DEFAULT_USERNAME = environ.get("OPERANDI_SERVER_DEFAULT_USERNAME")
OPERANDI_SERVER_DEFAULT_PASSWORD = environ.get("OPERANDI_SERVER_DEFAULT_PASSWORD")
OPERANDI_SERVER_URL_LOCAL = environ.get("OPERANDI_SERVER_URL_LOCAL", "http://localhost:48000")
OPERANDI_SERVER_URL_LIVE = environ.get("OPERANDI_SERVER_URL_LIVE", "http://localhost:48000")

OPERANDI_TESTS_LOCAL_DIR_WORKFLOW_JOBS = join(OPERANDI_SERVER_BASE_DIR, "workflow_jobs")
OPERANDI_TESTS_LOCAL_DIR_WORKFLOWS = join(OPERANDI_SERVER_BASE_DIR, "workflows")
OPERANDI_TESTS_LOCAL_DIR_WORKSPACES = join(OPERANDI_SERVER_BASE_DIR, "workspaces")
OPERANDI_TESTS_HPC_DIR_BATCH_SCRIPTS = join(OPERANDI_HPC_DIR_PROJECT, "batch_scripts")
OPERANDI_TESTS_HPC_DIR_SLURM_WORKSPACES = join(OPERANDI_HPC_DIR_PROJECT, "slurm_workspaces")
