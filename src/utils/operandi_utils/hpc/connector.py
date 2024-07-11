from logging import Logger
from os.path import exists, isfile
from paramiko import AutoAddPolicy, Channel, RSAKey, SSHClient, Transport
from pathlib import Path
from typing import List, Union

from .constants import HPC_SSH_CONNECTION_TRY_TIMES
from .utils import (
    resolve_hpc_user_home_dir, resolve_hpc_project_root_dir, resolve_hpc_batch_scripts_dir,
    resolve_hpc_slurm_workspaces_dir)


class HPCConnector:
    def __init__(
        self, hpc_hosts: List[str], proxy_hosts: List[str], username: str, project_username: str, key_path: Path,
        key_pass: Union[str, None], project_name: str, log: Logger,
        channel_keep_alive_interval: int = 30, connection_keep_alive_interval: int = 30, tunnel_host: str = 'localhost',
        tunnel_port: int = 0
    ) -> None:
        if not username:
            raise ValueError("Environment variable is probably not set: OPERANDI_HPC_USERNAME")
        if not project_username:
            raise ValueError("Environment variable is probably not set: OPERANDI_HPC_PROJECT_USERNAME")
        if not key_path:
            raise ValueError("Environment variable is probably not set: OPERANDI_HPC_SSH_KEYPATH")
        if not project_name:
            raise ValueError("Environment variable is probably not set: OPERANDI_HPC_PROJECT_NAME")
        self.log = log

        # The username is used to connect to the proxy server
        self.username = username
        # The project username is used to connect to the HPC front end to access the shared project folder
        self.project_username = project_username

        self.verify_pkey_file_existence(key_path)

        # Use the same private key for both the proxy and hpc connections
        self.proxy_key_path = key_path
        self.proxy_key_pass = key_pass
        self.hpc_key_path = key_path
        self.hpc_key_pass = key_pass

        self.connection_keep_alive_interval = connection_keep_alive_interval
        self.channel_keep_alive_interval = channel_keep_alive_interval

        # A list of hpc hosts - tries to connect to all until one is successful
        self.hpc_hosts = hpc_hosts
        self.last_used_hpc_host = None

        # A list of proxy hosts - tries to connect to all until one is successful
        self.proxy_hosts = proxy_hosts
        self.last_used_proxy_host = None

        self.ssh_proxy_client = None
        self.proxy_tunnel = None
        self.ssh_hpc_client = None
        self.sftp_client = None

        self.log.info(f"""
            HPCConnector initialized with:
            Username: {self.username}
            HPC hosts: {self.hpc_hosts}
            Private key for hpc hosts: {self.hpc_key_path}
            Proxy hosts: {self.proxy_hosts}
            Private key for proxy hosts: {self.proxy_key_path}
            """)

        self.project_name = project_name
        self.user_home_dir = resolve_hpc_user_home_dir(project_username)
        self.project_root_dir = resolve_hpc_project_root_dir(project_name)
        self.batch_scripts_dir = resolve_hpc_batch_scripts_dir(project_name)
        self.slurm_workspaces_dir = resolve_hpc_slurm_workspaces_dir(project_name)

        self.log.info(f"""
            Project name: {self.project_name}
            User home dir: {self.user_home_dir}
            Project root dir: {self.project_root_dir}
            Batch scripts root dir: {self.batch_scripts_dir}
            Slurm workspaces root dir: {self.slurm_workspaces_dir}
            """)

        self.tunnel_host = tunnel_host
        self.tunnel_port = tunnel_port
        self.create_ssh_connection_to_hpc_by_iteration(tunnel_host=tunnel_host, tunnel_port=tunnel_port)

    @staticmethod
    def verify_pkey_file_existence(key_path: Path):
        if not exists(key_path):
            raise FileNotFoundError(f"Private key path does not exist: {key_path}")
        if not isfile(key_path):
            raise FileNotFoundError(f"Private key path is not a file: {key_path}")

    def connect_to_proxy_server(self, host: str, port: int = 22) -> SSHClient:
        if self.ssh_proxy_client:
            self.log.warning(f"Closing the previously existing ssh proxy client")
            self.ssh_proxy_client.close()
            self.ssh_proxy_client = None
        self.ssh_proxy_client = SSHClient()
        self.log.debug(f"Setting missing host key policy for the proxy client")
        self.ssh_proxy_client.set_missing_host_key_policy(AutoAddPolicy())
        self.log.debug(f"Retrieving proxy server private key file from path: {self.proxy_key_path}")
        proxy_pkey = RSAKey.from_private_key_file(str(self.proxy_key_path), self.proxy_key_pass)
        self.log.info(f"Connecting to proxy server {host}:{port} with username: {self.username}")
        self.ssh_proxy_client.connect(
            hostname=host, port=port, username=self.username, pkey=proxy_pkey, passphrase=self.proxy_key_pass)
        # self.ssh_proxy_client.get_transport().set_keepalive(self.connection_keep_alive_interval)
        self.last_used_proxy_host = host
        self.log.debug(f"Successfully connected to the proxy server")
        return self.ssh_proxy_client

    def establish_proxy_tunnel(
        self, dst_host: str, dst_port: int = 22, src_host: str = 'localhost', src_port: int = 0,
        channel_kind: str = 'direct-tcpip',
    ) -> Channel:
        proxy_transport = self.ssh_proxy_client.get_transport()
        if self.proxy_tunnel:
            self.log.warning(f"Closing the previously existing ssh proxy tunel")
            self.proxy_tunnel.close()
            self.proxy_tunnel = None
        self.log.info(f"Configuring a tunnel to destination {dst_host}:{dst_port} from {src_host}:{src_port}")
        self.proxy_tunnel = proxy_transport.open_channel(
            kind=channel_kind, src_addr=(src_host, src_port), dest_addr=(dst_host, dst_port))
        # self.proxy_tunnel.get_transport().set_keepalive(self.channel_keep_alive_interval)
        self.last_used_hpc_host = dst_host
        self.log.debug(f"Successfully configured a proxy tunnel")
        return self.proxy_tunnel

    def connect_to_hpc_frontend_server(self, host: str, port: int = 22, proxy_tunnel: Channel = None) -> SSHClient:
        if self.ssh_hpc_client:
            self.log.warning(f"Closing the previously existing ssh hpc client")
            self.ssh_hpc_client.close()
            self.ssh_hpc_client = None
        self.ssh_hpc_client = SSHClient()
        self.log.debug(f"Setting missing host key policy for the hpc frontend client")
        self.ssh_hpc_client.set_missing_host_key_policy(AutoAddPolicy())
        self.log.debug(f"Retrieving hpc frontend server private key file from path: {self.hpc_key_path}")
        hpc_pkey = RSAKey.from_private_key_file(str(self.hpc_key_path), self.hpc_key_pass)
        self.log.info(f"Connecting to hpc frontend server {host}:{port} with project username: {self.project_username}")
        self.ssh_hpc_client.connect(hostname=host, port=port, username=self.project_username, pkey=hpc_pkey,
                                    passphrase=self.hpc_key_pass, sock=proxy_tunnel)
        # self.ssh_hpc_client.get_transport().set_keepalive(self.connection_keep_alive_interval)
        self.last_used_hpc_host = host
        self.log.debug(f"Successfully connected to the hpc frontend server")
        return self.ssh_hpc_client

    def is_transport_responsive(self, transport: Transport) -> bool:
        if not transport:
            self.log.warning("The transport is non-existing")
            return False
        if not transport.is_active():
            self.log.warning("The transport is non-active")
            return False
        try:
            # Sometimes is_active() returns false-positives, hence the extra check
            transport.send_ignore()
            # Nevertheless this still returns false-positives...!!!
            # https://github.com/paramiko/paramiko/issues/2026
            return True
        except EOFError as error:
            self.log.error(f"is_transport_responsive EOFError: {error}")
            return False

    def is_ssh_connection_still_responsive(self, ssh_client: SSHClient) -> bool:
        if not ssh_client:
            self.log.warning("The ssh client is non-existing")
            return False
        return self.is_transport_responsive(ssh_client.get_transport())

    def is_sftp_still_responsive(self) -> bool:
        if not self.sftp_client:
            self.log.warning("The sftp client is non-existing")
            return False
        channel = self.sftp_client.get_channel()
        if not channel:
            self.log.warning("The sftp client channel is non-existing")
            return False
        return self.is_transport_responsive(channel.get_transport())

    def reconnect_if_required(
        self, hpc_host: str = None, hpc_port: int = 22, proxy_host: str = None, proxy_port: int = 22,
        tunnel_host: str = 'localhost', tunnel_port: int = 0
    ) -> None:
        if not hpc_host:
            hpc_host = self.last_used_hpc_host
        if not proxy_host:
            proxy_host = self.last_used_proxy_host
        if not self.is_ssh_connection_still_responsive(self.ssh_proxy_client):
            self.log.warning("The connection to proxy server is not responsive, trying to open a new connection")
            self.ssh_proxy_client = self.connect_to_proxy_server(host=proxy_host, port=proxy_port)
        if not self.is_ssh_connection_still_responsive(self.proxy_tunnel):
            self.log.warning("The proxy tunnel is not responsive, trying to establish a new proxy tunnel")
            self.proxy_tunnel = self.establish_proxy_tunnel(hpc_host, hpc_port, tunnel_host, tunnel_port)
        if not self.is_ssh_connection_still_responsive(self.ssh_hpc_client):
            self.log.warning("The connection to hpc frontend server is not responsive, trying to open a new connection")
            self.ssh_hpc_client = self.connect_to_hpc_frontend_server(proxy_host, proxy_port, self.proxy_tunnel)

    def recreate_sftp_if_required(
        self, hpc_host: str = None, hpc_port: int = 22, proxy_host: str = None, proxy_port: int = 22,
        tunnel_host: str = 'localhost', tunnel_port: int = 0
    ) -> None:
        if not hpc_host:
            hpc_host = self.last_used_hpc_host
        if not proxy_host:
            proxy_host = self.last_used_proxy_host
        self.reconnect_if_required(hpc_host=hpc_host, hpc_port=hpc_port, proxy_host=proxy_host, proxy_port=proxy_port,
                                   tunnel_host=tunnel_host, tunnel_port=tunnel_port)
        if not self.is_sftp_still_responsive():
            self.log.warning("The SFTP client is not responsive, trying to create a new SFTP client")
            if self.sftp_client:
                self.sftp_client.close()
                self.sftp_client = None
            self.sftp_client = self.ssh_hpc_client.open_sftp()
            # self.sftp_client.get_channel().get_transport().set_keepalive(self.channel_keep_alive_interval)

    def create_ssh_connection_to_hpc_by_iteration(
        self, try_times: int = HPC_SSH_CONNECTION_TRY_TIMES, tunnel_host: str = 'localhost', tunnel_port: int = 0
    ) -> None:
        while try_times > 0:
            for proxy_host in self.proxy_hosts:
                self.ssh_proxy_client = None
                self.last_used_proxy_host = None
                for hpc_host in self.hpc_hosts:
                    self.ssh_hpc_client = None
                    self.last_used_hpc_host = None
                    try:
                        self.reconnect_if_required(
                            hpc_host=hpc_host, hpc_port=22,
                            proxy_host=proxy_host, proxy_port=22,
                            tunnel_host=tunnel_host, tunnel_port=tunnel_port)
                        return  # all connections were successful
                    except Exception as error:
                        self.log.error(f"""
                            Failed to connect to hpc host: {hpc_host}
                            Over proxy host: {proxy_host}
                            Exception Error: {error}
                        """)
                        continue
            try_times -= 1

        raise Exception(f"""
            Failed to establish connection to any of the HPC hosts: {self.hpc_hosts}
            Using the hpc private key: {self.hpc_key_path}
            Over any of the proxy hosts: {self.proxy_hosts}
            Using the proxy private key: {self.proxy_key_path}
            Performed connection iterations: {try_times}
        """)
