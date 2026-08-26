"""bash 工具测试:执行、退出码、超时、黑名单。全部本地、无网络。"""
import pytest
from tools_bash import bash


def test_echo_output_and_exit_code():
    result = bash("echo hello")
    assert "[退出码 0]" in result
    assert "hello" in result
    assert "【stdout】" in result


def test_nonzero_exit_code_reported():
    result = bash("exit 3")
    assert "[退出码 3]" in result


def test_stderr_section_present():
    result = bash("ls /definitely_not_a_real_dir_xyz")
    assert "【stderr】" in result


def test_empty_command_rejected():
    assert "命令为空" in bash("   ")


@pytest.mark.parametrize("cmd", ["rm -rf /tmp/x", "DEL /S C:\\x", "format c:"])
def test_dangerous_commands_blocked(cmd):
    assert "检测到危险命令片段" in bash(cmd)


def test_timeout_terminates_command():
    # MSYS/Git Bash 的 sleep;超时设 1s,命令要跑 5s
    assert "超时" in bash("sleep 5", timeout=1)


def test_blacklist_false_positive_documented():
    # 记录当前黑名单的已知误杀:echo shutdown 被拦。
    # 以后上「确认门」替代黑名单时,把这个测试改成断言正常输出。
    assert "检测到危险命令片段" in bash("echo shutdown")
