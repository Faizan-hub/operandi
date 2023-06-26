import json
import logging
import signal
from os import getppid, setsid
from os.path import join
from sys import exit

from operandi_utils import reconfigure_all_loggers
import operandi_utils.database.database as db
from operandi_utils.hpc import HPCExecutor, HPCTransfer
from operandi_utils.rabbitmq import RMQConsumer

from .constants import (
    LOG_LEVEL_WORKER,
    LOG_FILE_PATH_WORKER_PREFIX
)


# Each worker class listens to a specific queue,
# consume messages, and process messages.
class Worker:
    def __init__(self, db_url, rmq_host, rmq_port, rmq_vhost, rmq_username, rmq_password, queue_name, test_sbatch=False):
        self.log = logging.getLogger(__name__)
        self.queue_name = queue_name
        self.log_file_path = f"{LOG_FILE_PATH_WORKER_PREFIX}_{queue_name}.log"
        self.test_sbatch = test_sbatch

        self.db_url = db_url
        # Connection to RabbitMQ related parameters
        self.rmq_host = rmq_host
        self.rmq_port = rmq_port
        self.rmq_vhost = rmq_vhost
        self.rmq_username = rmq_username
        self.rmq_password = rmq_password
        self.rmq_consumer = None

        self.hpc_executor = None
        self.hpc_io_transfer = None

        # Currently consumed message related parameters
        self.current_message_delivery_tag = None
        self.current_message_ws_id = None
        self.current_message_wf_id = None
        self.current_message_job_id = None
        self.has_consumed_message = False

    def run(self):
        try:
            # Source: https://unix.stackexchange.com/questions/18166/what-are-session-leaders-in-ps
            # Make the current process session leader
            setsid()
            # Reconfigure all loggers to the same format
            reconfigure_all_loggers(
                log_level=LOG_LEVEL_WORKER,
                log_file_path=self.log_file_path
            )
            self.log.info(f"Activating signal handler for SIGINT, SIGTERM")
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            db.sync_initiate_database(self.db_url)

            # Connect the HPC Executor
            self.hpc_executor = HPCExecutor()
            if self.hpc_executor:
                self.hpc_executor.connect()
                self.log.info("HPC executor connection successful.")
            else:
                self.log.error("HPC executor connection has failed.")

            # Connect the HPC IO Transfer
            self.hpc_io_transfer = HPCTransfer()
            if self.hpc_io_transfer:
                self.hpc_io_transfer.connect()
                self.log.info("HPC transfer connection successful.")
            else:
                self.log.error("HPC transfer connection has failed.")
            self.log.info("Worker runs jobs in HPC.")

            self.connect_consumer()
            self.configure_consuming(self.queue_name, self.__on_message_consumed_callback_hpc)

            self.start_consuming()
        except Exception as e:
            self.log.error(f"The worker failed to run, reason: {e}")
            raise Exception(f"The worker failed to run, reason: {e}")

    def connect_consumer(self):
        if self.rmq_consumer:
            # If for some reason connect_consumer() is called more than once.
            self.log.warning(f"The RMQConsumer was already instantiated. "
                             f"Overwriting the existing RMQConsumer.")
        self.log.info(f"Connecting RMQConsumer to RabbitMQ server: "
                      f"{self.rmq_host}:{self.rmq_port}{self.rmq_vhost}")
        self.rmq_consumer = RMQConsumer(host=self.rmq_host, port=self.rmq_port, vhost=self.rmq_vhost)
        # TODO: Remove this information before the release
        self.log.debug(f"RMQConsumer authenticates with username: "
                       f"{self.rmq_username}, password: {self.rmq_password}")
        self.rmq_consumer.authenticate_and_connect(username=self.rmq_username, password=self.rmq_password)
        self.log.info(f"Successfully connected RMQConsumer.")

    def configure_consuming(self, queue_name, callback_method):
        if not self.rmq_consumer:
            raise Exception("The RMQConsumer connection is not configured or broken")
        self.log.info(f"Configuring the consuming for queue: {queue_name}")
        self.rmq_consumer.configure_consuming(
            queue_name=queue_name,
            callback_method=callback_method
        )

    def start_consuming(self):
        if not self.rmq_consumer:
            raise Exception("The RMQConsumer connection is not configured or broken")
        self.log.info(f"Starting consuming from queue: {self.queue_name}")
        self.rmq_consumer.start_consuming()

    def __on_message_consumed_callback_hpc(self, ch, method, properties, body):
        self.log.debug(f"ch: {ch}, method: {method}, properties: {properties}, body: {body}")
        self.log.debug(f"Consumed message: {body}")

        self.current_message_delivery_tag = method.delivery_tag
        self.has_consumed_message = True

        # Since the workflow_message is constructed by the Operandi Server,
        # it should not fail here when parsing under normal circumstances.
        try:
            consumed_message = json.loads(body)
            self.log.info(f"Consumed message: {consumed_message}")
            self.current_message_ws_id = consumed_message["workspace_id"]
            self.current_message_wf_id = consumed_message["workflow_id"]
            self.current_message_job_id = consumed_message["job_id"]
            input_file_grp = consumed_message["input_file_grp"]
        except Exception as error:
            self.log.error(f"Parsing the consumed message has failed: {error}")
            self.__handle_message_failure(interruption=False)
            return

        # Handle database related reads and set the workflow job status to RUNNING
        try:
            # TODO: This should be optimized, i.e., single read to the DB instead of three
            workflow_db = db.sync_get_workflow(self.current_message_wf_id)
            workspace_db = db.sync_get_workspace(self.current_message_ws_id)
            workflow_job_db = db.sync_get_workflow_job(self.current_message_job_id)

            workflow_script_path = workflow_db.workflow_script_path
            workspace_dir = workspace_db.workspace_dir
            mets_basename = workspace_db.mets_basename
            if not mets_basename:
                mets_basename = "mets.xml"

        except Exception as error:
            self.log.error(f"Database related error has occurred: {error}")
            self.__handle_message_failure(interruption=False)
            return

        # Trigger a slurm job in the HPC
        try:
            self.prepare_and_trigger_slurm_job(
                workflow_job_id=self.current_message_job_id,
                workspace_id=self.current_message_ws_id,
                workspace_dir=workspace_dir,
                workspace_base_mets=mets_basename,
                workflow_script_path=workflow_script_path,
                input_file_grp=input_file_grp
            )
        except Exception as error:
            self.log.error(f"Triggering a slurm job in the HPC has failed: {error}")
            self.__handle_message_failure(interruption=False)
            return

        self.log.debug(f"The HPC slurm job was successfully submitted")
        job_state = "RUNNING"
        self.log.info(f"Setting new job state[{job_state}] of job_id: {self.current_message_job_id}")
        db.sync_set_workflow_job_state(self.current_message_job_id, job_state=job_state)
        self.has_consumed_message = False
        self.log.debug(f"Acking delivery tag: {self.current_message_delivery_tag}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def __handle_message_failure(self, interruption: bool = False):
        job_state = "FAILED"
        self.log.info(f"Setting new state[{job_state}] of job_id: {self.current_message_job_id}")
        db.sync_set_workflow_job_state(
            job_id=self.current_message_job_id,
            job_state=job_state
        )
        self.has_consumed_message = False

        if interruption:
            # self.log.debug(f"Nacking delivery tag: {self.current_message_delivery_tag}")
            # self.rmq_consumer._channel.basic_nack(delivery_tag=self.current_message_delivery_tag)
            # TODO: Sending ACK for now because it is hard to clean up without a mets workspace backup mechanism
            self.log.debug(f"Interruption Acking delivery tag: {self.current_message_delivery_tag}")
            self.rmq_consumer._channel.basic_ack(delivery_tag=self.current_message_delivery_tag)
            return

        self.log.debug(f"Acking delivery tag: {self.current_message_delivery_tag}")
        self.rmq_consumer._channel.basic_ack(delivery_tag=self.current_message_delivery_tag)

        # Reset the current message related parameters
        self.current_message_delivery_tag = None
        self.current_message_ws_id = None
        self.current_message_wf_id = None
        self.current_message_job_id = None

    # TODO: Ideally this method should be wrapped to be able
    #  to pass internal data from the Worker class required for the cleaning
    # The arguments to this method are passed by the caller from the OS
    def signal_handler(self, sig, frame):
        signal_name = signal.Signals(sig).name
        self.log.info(f"{signal_name} received from parent process[{getppid()}].")
        if self.has_consumed_message:
            self.log.info(f"Handling the message failure due to interruption: {signal_name}")
            self.__handle_message_failure(interruption=True)

        # TODO: Disconnect the RMQConsumer properly
        # TODO: Clean the remaining leftovers (if any)
        self.rmq_consumer._channel.close()
        self.rmq_consumer = None
        self.log.info("Exiting gracefully.")
        exit(0)

    # TODO: This should be further refined, currently it's just everything in one place
    def prepare_and_trigger_slurm_job(
            self,
            workflow_job_id,
            workspace_id,
            workspace_dir,
            workspace_base_mets,
            workflow_script_path,
            input_file_grp
    ) -> str:

        if self.test_sbatch:
            batch_script_id = "test_submit_workflow_job.sh"
        else:
            batch_script_id = "submit_workflow_job.sh"

        hpc_batch_script_path = self.hpc_io_transfer.put_batch_script(
            batch_script_id=batch_script_id
        )

        try:
            hpc_slurm_workspace_path = self.hpc_io_transfer.pack_and_put_slurm_workspace(
                ocrd_workspace_dir=workspace_dir,
                workflow_job_id=workflow_job_id,
                nextflow_script_path=workflow_script_path,
                tempdir_prefix="slurm_workspace-"
            )
        except Exception as error:
            raise Exception(f"Failed to pack and put slurm workspace: {error}")

        try:
            # NOTE: The paths below must be a valid existing path inside the HPC
            slurm_job_id = self.hpc_executor.trigger_slurm_job(
                batch_script_path=hpc_batch_script_path,
                workflow_job_id=workflow_job_id,
                nextflow_script_path=workflow_script_path,
                workspace_id=workspace_id,
                mets_basename=workspace_base_mets,
                input_file_grp=input_file_grp
            )
        except Exception as error:
            raise Exception(f"Triggering slurm job failed: {error}")

        try:
            db.sync_save_hpc_slurm_job(
                workflow_job_id=workflow_job_id,
                hpc_slurm_job_id=slurm_job_id,
                hpc_batch_script_path=hpc_batch_script_path,
                hpc_slurm_workspace_path=join(hpc_slurm_workspace_path, workflow_job_id)
            )
        except Exception as error:
            raise Exception(f"Failed to save the hpc slurm job in DB: {error}")
        return slurm_job_id

    def check_slurm_job_and_get_results(
            self,
            slurm_job_id,
            workspace_dir,
            workflow_job_dir,
            hpc_slurm_workspace_path
    ):
        try:
            finished_successfully = self.hpc_executor.poll_till_end_slurm_job_state(
                slurm_job_id=slurm_job_id,
                interval=10,
                timeout=60  # seconds, i.e., 60 seconds
            )
        except Exception as error:
            raise Exception(f"Polling job status has failed: {error}")

        if finished_successfully:
            self.hpc_io_transfer.get_and_unpack_slurm_workspace(
                ocrd_workspace_dir=workspace_dir,
                workflow_job_dir=workflow_job_dir,
                hpc_slurm_workspace_path=hpc_slurm_workspace_path
            )
            # Delete the result dir from the HPC home folder
            # self.hpc_executor.execute_blocking(f"bash -lc 'rm -rf {hpc_slurm_workspace_path}/{workflow_job_id}'")
        else:
            raise Exception(f"Slurm job has failed: {slurm_job_id}")
