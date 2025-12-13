# test_runner.py
import subprocess
import os
import sys
import ast
import uuid
import json


class PytestRunner:
    def __init__(self, workspace="temp_tests"):
        self.workspace = workspace
        if not os.path.exists(workspace):
            os.makedirs(workspace)

    def _security_scan(self, code_content):
        """AST 静态安全扫描"""
        forbidden_calls = [
            'os.system', 'os.popen', 'subprocess.call', 'subprocess.Popen',
            'shutil.rmtree', 'os.remove', 'exec', 'eval'
        ]

        try:
            tree = ast.parse(code_content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # 检查函数调用
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        try:
                            func_name = f"{node.func.value.id}.{node.func.attr}"
                        except:
                            pass

                    for bad in forbidden_calls:
                        if bad in func_name:
                            return False, f"检测到危险代码调用: {func_name}"
        except Exception as e:
            return False, f"代码解析错误: {str(e)}"

        return True, "Safe"

    def run_single_case_stream(self, case_id, code_content, extra_env=None, log_callback=None):
        # 1. 安全检查
        is_safe, reason = self._security_scan(code_content)
        if not is_safe:
            msg = f"🚫 安全拦截: {reason}"
            if log_callback: log_callback(msg)
            return False, msg

        # 2. 写入临时文件
        unique_id = uuid.uuid4().hex[:8]
        filename = f"test_{case_id}_{unique_id}.py"
        filepath = os.path.join(self.workspace, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code_content)
        except Exception as e:
            return False, f"写入测试文件失败: {str(e)}"

        # =========================================================
        # 3. 环境变量准备 (优化版)
        # =========================================================
        env = os.environ.copy()

        # 确保 PYTHONPATH 包含项目根目录，以便能 import utils
        current_root = os.getcwd()
        env["PYTHONPATH"] = current_root + os.pathsep + env.get("PYTHONPATH", "")
        # 强制无缓冲输出，保证流式日志实时性
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        if extra_env:
            # 用于显示的脱敏日志字典
            masked_log = {}

            for k, v in extra_env.items():
                # 关键：强制转为字符串，防止 subprocess 报错
                str_k, str_v = str(k).strip(), str(v).strip()

                # 注入真实环境
                env[str_k] = str_v

                # 脱敏处理：如果 key 包含敏感词，在日志中隐藏 value
                if any(s in str_k.upper() for s in ['TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'AUTH']):
                    masked_log[str_k] = "******"
                else:
                    masked_log[str_k] = str_v

            # 打印清爽的调试日志
            print(f"[Runner] {case_id} 环境变量注入: {json.dumps(masked_log, ensure_ascii=False)}")
        else:
            print(f"[Runner] {case_id} 无额外环境变量注入")

        # =========================================================

        # 4. 执行测试
        cmd = [sys.executable, "-m", "pytest", filepath, "-s", "-v"]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,  # 传入处理好的 env
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )

        full_logs = []
        while True:
            try:
                line = process.stdout.readline()
                if not line and process.poll() is not None: break
                if line:
                    l = line.rstrip()
                    full_logs.append(l)
                    # 实时回调给 UI
                    if log_callback: log_callback(l)
            except:
                break

        return_code = process.poll()

        # 5. 清理文件
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass

        return (return_code == 0), "\n".join(full_logs)