"""Session Manager - 서버 계정 잠금/해제 및 프로세스 관리"""
import logging
from dataclasses import dataclass

from app.models.server_resource import ServerResource
from app.services.ssh_runner import SSHResult, run_command

logger = logging.getLogger(__name__)


@dataclass
class SessionOperationResult:
    """세션 작업 결과"""
    ok: bool
    message: str
    details: dict | None = None


class SessionManager:
    """서버 세션 관리 서비스"""

    @staticmethod
    def unlock_user(server: ServerResource, account_name: str) -> SessionOperationResult:
        """
        사용자 계정 잠금 해제 (로그인 허용)
        
        Args:
            server: 대상 서버
            account_name: 잠금 해제할 계정명
            
        Returns:
            SessionOperationResult
        """
        if not server.host or not server.ssh_username or not server.ssh_private_key:
            return SessionOperationResult(
                ok=False,
                message="Server SSH configuration is incomplete",
                details={"account": account_name}
            )

        command = f"sudo usermod -U {account_name}"
        
        result = run_command(
            host=server.host,
            command=command,
            port=server.ssh_port,
            username=server.ssh_username,
            private_key=server.ssh_private_key,
            timeout_sec=15.0,
        )

        if result.ok:
            logger.info(f"Unlocked user account '{account_name}' on server '{server.name}'")
            return SessionOperationResult(
                ok=True,
                message=f"User '{account_name}' unlocked successfully",
                details={"account": account_name, "stdout": result.stdout}
            )
        else:
            logger.error(f"Failed to unlock user '{account_name}' on server '{server.name}': {result.message}")
            return SessionOperationResult(
                ok=False,
                message=result.message,
                details={"account": account_name, "stderr": result.stderr}
            )

    @staticmethod
    def lock_user(server: ServerResource, account_name: str) -> SessionOperationResult:
        """
        사용자 계정 잠금 (로그인 차단)
        
        Args:
            server: 대상 서버
            account_name: 잠금할 계정명
            
        Returns:
            SessionOperationResult
        """
        if not server.host or not server.ssh_username or not server.ssh_private_key:
            return SessionOperationResult(
                ok=False,
                message="Server SSH configuration is incomplete",
                details={"account": account_name}
            )

        command = f"sudo usermod -L {account_name}"
        
        result = run_command(
            host=server.host,
            command=command,
            port=server.ssh_port,
            username=server.ssh_username,
            private_key=server.ssh_private_key,
            timeout_sec=15.0,
        )

        if result.ok:
            logger.info(f"Locked user account '{account_name}' on server '{server.name}'")
            return SessionOperationResult(
                ok=True,
                message=f"User '{account_name}' locked successfully",
                details={"account": account_name, "stdout": result.stdout}
            )
        else:
            logger.error(f"Failed to lock user '{account_name}' on server '{server.name}': {result.message}")
            return SessionOperationResult(
                ok=False,
                message=result.message,
                details={"account": account_name, "stderr": result.stderr}
            )

    @staticmethod
    def kill_user_processes(
        server: ServerResource,
        account_name: str,
        force: bool = False
    ) -> SessionOperationResult:
        """
        사용자의 모든 프로세스 종료
        
        Args:
            server: 대상 서버
            account_name: 프로세스를 종료할 계정명
            force: True이면 -9 (SIGKILL) 사용
            
        Returns:
            SessionOperationResult
        """
        if not server.host or not server.ssh_username or not server.ssh_private_key:
            return SessionOperationResult(
                ok=False,
                message="Server SSH configuration is incomplete",
                details={"account": account_name}
            )

        signal_flag = "-9" if force else ""
        command = f"sudo pkill -u {account_name} {signal_flag}".strip()
        
        result = run_command(
            host=server.host,
            command=command,
            port=server.ssh_port,
            username=server.ssh_username,
            private_key=server.ssh_private_key,
            timeout_sec=20.0,
        )

        # pkill은 프로세스가 없으면 exit code 1 반환 (정상)
        # exit code 0: 프로세스 종료함
        # exit code 1: 종료할 프로세스 없음 (매칭된 프로세스 없음 = 정상)
        # exit code 2+: 에러
        if result.ok or result.message == "Exit code 1" or "no process found" in result.stderr.lower():
            signal_type = "SIGKILL" if force else "SIGTERM"
            logger.info(f"Killed processes for user '{account_name}' on server '{server.name}' ({signal_type})")
            return SessionOperationResult(
                ok=True,
                message=f"Processes killed for user '{account_name}' ({signal_type})",
                details={
                    "account": account_name,
                    "force": force,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            )
        else:
            logger.warning(f"Failed to kill processes for user '{account_name}' on server '{server.name}': {result.message}")
            return SessionOperationResult(
                ok=False,
                message=result.message,
                details={
                    "account": account_name,
                    "force": force,
                    "stderr": result.stderr
                }
            )

    @staticmethod
    def get_all_users(server: ServerResource) -> SessionOperationResult:
        """
        서버의 모든 일반 사용자 계정 목록 조회
        
        일반 사용자: UID >= 1000인 계정
        
        Args:
            server: 대상 서버
            
        Returns:
            SessionOperationResult with details['users'] = list of usernames
        """
        if not server.host or not server.ssh_username or not server.ssh_private_key:
            return SessionOperationResult(
                ok=False,
                message="Server SSH configuration is incomplete"
            )

        # UID >= 1000인 계정만 추출 (일반 사용자)
        command = "getent passwd | awk -F: '$3 >= 1000 {print $1}'"
        
        result = run_command(
            host=server.host,
            command=command,
            port=server.ssh_port,
            username=server.ssh_username,
            private_key=server.ssh_private_key,
            timeout_sec=15.0,
        )

        if result.ok:
            users = [
                line.strip()
                for line in result.stdout.strip().split('\n')
                if line.strip()
            ]
            logger.info(f"Retrieved {len(users)} user accounts from server '{server.name}'")
            return SessionOperationResult(
                ok=True,
                message=f"Retrieved {len(users)} user accounts",
                details={"users": users}
            )
        else:
            logger.error(f"Failed to retrieve user list from server '{server.name}': {result.message}")
            return SessionOperationResult(
                ok=False,
                message=result.message,
                details={"stderr": result.stderr}
            )

    @staticmethod
    def lock_all_except(
        server: ServerResource,
        exception_accounts: set[str]
    ) -> SessionOperationResult:
        """
        예외 계정을 제외한 모든 일반 사용자 계정 잠금
        
        Args:
            server: 대상 서버
            exception_accounts: 잠금하지 않을 계정 목록
            
        Returns:
            SessionOperationResult with details about locked accounts
        """
        # 모든 사용자 조회
        users_result = SessionManager.get_all_users(server)
        if not users_result.ok:
            return users_result

        all_users = users_result.details.get("users", [])
        locked = []
        failed = []

        for user in all_users:
            if user in exception_accounts:
                logger.debug(f"Skipping exception account '{user}' on server '{server.name}'")
                continue

            lock_result = SessionManager.lock_user(server, user)
            if lock_result.ok:
                locked.append(user)
            else:
                failed.append({"user": user, "error": lock_result.message})

        logger.info(f"Locked {len(locked)} accounts on server '{server.name}', {len(failed)} failed")
        return SessionOperationResult(
            ok=len(failed) == 0,
            message=f"Locked {len(locked)} accounts, {len(failed)} failed",
            details={
                "locked": locked,
                "failed": failed,
                "exception_accounts": list(exception_accounts)
            }
        )

    @staticmethod
    def kill_processes_except(
        server: ServerResource,
        exception_accounts: set[str]
    ) -> SessionOperationResult:
        """
        예외 계정을 제외한 모든 일반 사용자의 프로세스 종료
        
        Args:
            server: 대상 서버
            exception_accounts: 프로세스를 종료하지 않을 계정 목록
            
        Returns:
            SessionOperationResult with details about killed processes
        """
        # 모든 사용자 조회
        users_result = SessionManager.get_all_users(server)
        if not users_result.ok:
            return users_result

        all_users = users_result.details.get("users", [])
        killed = []
        failed = []

        for user in all_users:
            if user in exception_accounts:
                logger.debug(f"Skipping exception account '{user}' on server '{server.name}'")
                continue

            kill_result = SessionManager.kill_user_processes(server, user, force=False)
            if kill_result.ok:
                killed.append(user)
            else:
                failed.append({"user": user, "error": kill_result.message})

        logger.info(f"Killed processes for {len(killed)} accounts on server '{server.name}', {len(failed)} failed")
        return SessionOperationResult(
            ok=len(failed) == 0,
            message=f"Killed processes for {len(killed)} accounts, {len(failed)} failed",
            details={
                "killed": killed,
                "failed": failed,
                "exception_accounts": list(exception_accounts)
            }
        )
