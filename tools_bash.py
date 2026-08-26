"""高危工具 -- bash:执行 shell 命令,带危险命令黑名单、超时与输出截断。"""
import subprocess


def bash(command: str, timeout: int = 30):
    cmd = command.strip()
    if not cmd:
        return "命令为空,请提供要执行的命令"
    cmd_lower = cmd.lower()  # 命令小写化
    DANGEROUS = ["rm -rf", "rd /s", "del /s", "format ", "mkfs", "shutdown", "diskpart"]
    for d in DANGEROUS:
        if d in cmd_lower:
            return f"检测到危险命令片段「{d}」,已拒绝执行: {cmd}"
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=timeout,
        )

        def decode(b):
            if not b:
                return ""
            for enc in ("utf-8", "gbk"):  # Windows cmd 中文默认 GBK,先试 utf-8 再回退
                try:
                    return b.decode(enc)
                except UnicodeDecodeError:
                    continue
            return b.decode("utf-8", errors="replace")

        out, err = decode(proc.stdout), decode(proc.stderr)
        # 截断,防 context 爆炸(和 fetch_url 的 10000 同理)
        MAX = 8000
        if len(out) > MAX:
            out = out[:MAX] + f"\n...[输出过长,已截断(共 {len(proc.stdout)} 字符)]"
        if len(err) > MAX:
            err = err[:MAX] + "\n...[错误过长,已截断]"

        parts = [f"[退出码 {proc.returncode}]"]
        if out.strip():
            parts.append("【stdout】\n" + out)
        if err.strip():
            parts.append("【stderr】\n" + err)
        return "\n\n".join(parts)

    except subprocess.TimeoutExpired:
        return f"⏱️ 命令超时(>{timeout}s),已终止: {cmd}"
    except OSError as e:
        return f"执行失败:{type(e).__name__}: {e}"