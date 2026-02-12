"""Run commands on remote servers via SSH (paramiko)."""
import io
import logging
from dataclasses import dataclass

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class SSHResult:
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


def run_command(
    host: str,
    command: str,
    *,
    port: int = 22,
    username: str | None = None,
    private_key: str | None = None,
    timeout_sec: float = 10.0,
) -> SSHResult:
    """
    Execute a command on a remote host via SSH.
    Uses private_key (PEM string) for authentication.
    """
    if not host or not host.strip():
        return SSHResult(ok=False, message="Host is required")
    if not username or not username.strip():
        return SSHResult(ok=False, message="SSH username is required")
    if not private_key or not private_key.strip():
        return SSHResult(ok=False, message="SSH private key is required")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        key_file = io.StringIO(private_key.strip())
        try:
            pkey = paramiko.RSAKey.from_private_key(key_file)
        except paramiko.ssh_exception.SSHException:
            key_file.seek(0)
            pkey = paramiko.Ed25519Key.from_private_key(key_file)
        except Exception as e:
            logger.warning("SSH key parse error: %s", e)
            return SSHResult(
                ok=False,
                message=f"Invalid SSH private key: {e!s}",
            )

        client.connect(
            hostname=host.strip(),
            port=port,
            username=username.strip(),
            pkey=pkey,
            timeout=timeout_sec,
            banner_timeout=timeout_sec,
            auth_timeout=timeout_sec,
        )

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout_sec)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()

        return SSHResult(
            ok=(exit_status == 0),
            message="OK" if exit_status == 0 else f"Exit code {exit_status}",
            stdout=out,
            stderr=err,
        )
    except paramiko.AuthenticationException as e:
        logger.warning("SSH auth failed to %s: %s", host, e)
        return SSHResult(ok=False, message=f"Authentication failed: {e!s}")
    except paramiko.SSHException as e:
        logger.warning("SSH error to %s: %s", host, e)
        return SSHResult(ok=False, message=f"SSH error: {e!s}")
    except TimeoutError as e:
        logger.warning("SSH timeout to %s: %s", host, e)
        return SSHResult(ok=False, message=f"Connection timeout: {e!s}")
    except OSError as e:
        logger.warning("SSH connect error to %s: %s", host, e)
        return SSHResult(ok=False, message=f"Connection failed: {e!s}")
    finally:
        client.close()
