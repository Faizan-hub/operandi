from logging import getLogger
from pathlib import Path
from time import sleep

from operandi_utils.constants import StateJobSlurm
from .constants import (
    HPC_JOB_DEADLINE_TIME_TEST, HPC_JOB_QOS_DEFAULT, HPC_NHR_JOB_DEFAULT_PARTITION, HPC_BATCH_SUBMIT_WORKFLOW_JOB,
    HPC_WRAPPER_SUBMIT_WORKFLOW_JOB, HPC_WRAPPER_CHECK_WORKFLOW_JOB_STATUS
)
from .nhr_connector import NHRConnector

class NHRExecutor(NHRConnector):
    def __init__(self) -> None:
        logger = getLogger(name=self.__class__.__name__)
        super().__init__(logger)
        _ = self.ssh_client  # forces a connection

    # Execute blocking commands and wait for an output and return code
    def execute_blocking(self, command, timeout=None, environment=None):
        stdin, stdout, stderr = self.ssh_client.exec_command(
            command=command, timeout=timeout, environment=environment)

        # TODO: Not satisfied with this but fast conversion from
        #  SSHLibrary to Paramiko is needed for testing
        while not stdout.channel.exit_status_ready():
            sleep(1)
            continue

        output = stdout.readlines()
        err = stderr.readlines()
        return_code = stdout.channel.recv_exit_status()
        return output, err, return_code

    def trigger_slurm_job(
        self, workflow_job_id: str, nextflow_script_path: Path, input_file_grp: str,
        workspace_id: str, mets_basename: str, nf_process_forks: int, ws_pages_amount: int, use_mets_server: bool,
        file_groups_to_remove: str, cpus: int = 2, ram: int = 8, job_deadline_time: str = HPC_JOB_DEADLINE_TIME_TEST,
        partition: str = HPC_NHR_JOB_DEFAULT_PARTITION, qos: str = HPC_JOB_QOS_DEFAULT
    ) -> str:
        if ws_pages_amount < nf_process_forks:
            self.logger.warning(
                "The amount of workspace pages is less than the amount of requested Nextflow process forks. "
                f"The pages amount: {ws_pages_amount}, forks requested: {nf_process_forks}. "
                f"Setting the forks value to the value of amount of pages.")
            nf_process_forks = ws_pages_amount

        nextflow_script_id = nextflow_script_path.name
        use_mets_server_bash_flag = "true" if use_mets_server else "false"

        command = f"{HPC_WRAPPER_SUBMIT_WORKFLOW_JOB}"

        # SBATCH arguments passed to the batch script
        command += f" {partition}"
        command += f" {job_deadline_time}"
        command += f" {self.slurm_workspaces_dir}/{workflow_job_id}/slurm-job-%J.txt"
        command += f" {cpus}"
        command += f" {ram}G"
        command += f" {qos}"

        # Regular arguments passed to the batch script
        command += f" {HPC_BATCH_SUBMIT_WORKFLOW_JOB}"
        command += f" {self.slurm_workspaces_dir}"
        command += f" {workflow_job_id}"
        command += f" {nextflow_script_id}"
        command += f" {input_file_grp}"
        command += f" {workspace_id}"
        command += f" {mets_basename}"
        command += f" {cpus}"
        command += f" {ram}"
        command += f" {nf_process_forks}"
        command += f" {ws_pages_amount}"
        command += f" {use_mets_server_bash_flag}"
        command += f" {file_groups_to_remove}"

        self.logger.info(f"About to execute a force command: {command}")
        output, err, return_code = self.execute_blocking(command)
        self.logger.info(f"Command output: {output}")
        self.logger.info(f"Command err: {err}")
        self.logger.info(f"Command return code: {return_code}")
        slurm_job_id = output[0].strip('\n').split(' ')[-1]
        self.logger.info(f"Slurm job id: {slurm_job_id}")
        assert int(slurm_job_id)
        return slurm_job_id

    def check_slurm_job_state(self, slurm_job_id: str, tries: int = 10, wait_time: int = 2) -> str:
        command = f"{HPC_WRAPPER_CHECK_WORKFLOW_JOB_STATUS} {slurm_job_id}"
        slurm_job_state = None

        while not slurm_job_state and tries > 0:
            self.logger.info(f"About to execute a force command: {command}")
            output, err, return_code = self.execute_blocking(command)
            self.logger.info(f"Command output: {output}")
            self.logger.info(f"Command err: {err}")
            self.logger.info(f"Command return code: {return_code}")
            if output:
                if len(output) < 3:
                    self.logger.warning("The output has returned with less than 3 lines. "
                                        "The job has not been listed yet.")
                    continue
                # Split the last line and get the second element,
                # i.e., the state element in the requested output format
                slurm_job_state = output[-2].split()[1]
                # TODO: dirty fast fix, improve this
                if slurm_job_state.startswith('---'):
                    self.logger.warning("The output is dashes. The job has not been listed yet.")
                    slurm_job_state = None
                    continue
            if slurm_job_state:
                break
            tries -= 1
            sleep(wait_time)
        if not slurm_job_state:
            self.logger.warning(f"Returning a None slurm job state")
        self.logger.info(f"Slurm job state of {slurm_job_id}: {slurm_job_state}")
        return slurm_job_state

    def poll_till_end_slurm_job_state(self, slurm_job_id: str, interval: int = 5, timeout: int = 300) -> bool:
        self.logger.info(f"Polling slurm job status till end")
        tries_left = timeout / interval
        self.logger.info(f"Tries to be performed: {tries_left}")
        while tries_left:
            self.logger.info(f"Sleeping for {interval} secs")
            sleep(interval)
            tries_left -= 1
            self.logger.info(f"Tries left: {tries_left}")
            slurm_job_state = self.check_slurm_job_state(slurm_job_id)
            if not slurm_job_state:
                self.logger.info(f"Slurm job state is not available yet")
                continue
            if StateJobSlurm.is_state_success(slurm_job_state):
                self.logger.info(f"Slurm job state is in: {StateJobSlurm.success_states()}")
                return True
            if StateJobSlurm.is_state_waiting(slurm_job_state):
                self.logger.info(f"Slurm job state is in: {StateJobSlurm.waiting_states()}")
                continue
            if StateJobSlurm.is_state_running(slurm_job_state):
                self.logger.info(f"Slurm job state is in: {StateJobSlurm.running_states()}")
                continue
            if StateJobSlurm.is_state_fail(slurm_job_state):
                self.logger.info(f"Slurm job state is in: {StateJobSlurm.failing_states()}")
                return False
            # Sometimes the slurm state is still
            # not initialized inside the HPC environment.
            # This is not a problem that requires a raise of Exception
            self.logger.warning(f"Invalid SLURM job state: {slurm_job_state}")

        # Timeout reached
        self.logger.info("Polling slurm job status timeout reached")
        return False
