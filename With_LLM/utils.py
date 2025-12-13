# utils.py
import re
import json
import uuid
import time
import os
import requests
from faker import Faker

fake = Faker("zh_CN")


# ================= 1. 智能环境上下文读取 =================
def get_app_context(key, default=None, required=False):
    """
    统一变量读取器：解决大小写不一致导致的读取失败问题。
    例如：代码查 'receive_id'，能自动读到环境变量里的 'RECEIVE_ID' 或 'receive_id'。
    """
    target_key = str(key).strip()

    # 1. 尝试直接匹配
    val = os.environ.get(target_key)
    if val: return val

    # 2. 尝试全大写 (常见环境变量格式)
    val = os.environ.get(target_key.upper())
    if val: return val

    # 3. 尝试全小写
    val = os.environ.get(target_key.lower())
    if val: return val

    if required:
        raise ValueError(f"❌ 缺少必要环境变量: {target_key} (已尝试大写/小写查找)")

    return default


# ================= 2. 公共 HTTP 客户端 =================
class APIClient:
    def __init__(self, host, token=None):
        self.host = host.rstrip('/')
        self.token = token
        self.headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def request(self, method, endpoint, params=None, json_data=None, data=None, headers=None, **kwargs):
        url = f"{self.host}{endpoint}"
        print(f"\n🚀 Request: {method} {url}")

        # 合并自定义 headers
        req_headers = self.headers.copy()
        if headers:
            req_headers.update(headers)

        # 🌟 关键修复：如果是文件上传/表单提交 (data不为空 且 json_data为空)
        # 必须移除默认的 Content-Type: application/json，否则 requests 无法自动生成 boundary
        if data is not None and json_data is None:
            if "Content-Type" in req_headers:
                del req_headers["Content-Type"]

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=req_headers,
                params=params,
                json=json_data,
                data=data,
                timeout=10,
                **kwargs
            )
            return response
        except Exception as e:
            print(f"🔴 请求异常: {str(e)}")
            raise


# ================= 3. 辅助工具函数 =================
def extract_code_block(text):
    """
    提取 Markdown 代码块 (修复版：自动去除语言标记)
    解决: LLM 返回 ```json ... ``` 时，提取结果包含 'json' 单词导致运行报错的问题
    """
    if "```" not in text:
        return text.strip()

    # 1. 精确匹配 python 代码块
    match_py = re.search(r"```python\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match_py:
        return match_py.group(1).strip()

    # 2. 通用匹配：尝试捕获语言标记 (如 json, py, python) 并丢弃它
    # 匹配 ```word<换行>content```
    match_with_lang = re.search(r"```[a-zA-Z]+\n([\s\S]*?)```", text, re.IGNORECASE)
    if match_with_lang:
        return match_with_lang.group(1).strip()

    # 3. 最宽泛匹配 (兜底)
    match_generic = re.search(r"```\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match_generic:
        return match_generic.group(1).strip()

    return text.strip()


def repair_json_content(text):
    text = text.strip()

    # 1. 尝试提取 Markdown 代码块 (```json ... ```)
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.DOTALL | re.IGNORECASE)
        if match: text = match.group(1).strip()

    # 2. 暴力截取最外层 {} 或 []
    start_idx = -1
    for i, char in enumerate(text):
        if char in ['{', '[']:
            start_idx = i
            break

    if start_idx != -1:
        last_brace = text.rfind('}' if text[start_idx] == '{' else ']')
        if last_brace != -1:
            text = text[start_idx: last_brace + 1]

    # 3. 清理 LLM 尾部注释
    lines = [re.sub(r"\s*//.*$", "", line) for line in text.split('\n')]
    text = "\n".join(lines)

    # 4. 自动修复漏掉的逗号
    text = re.sub(r"}\s*\{", "}, {", text)
    text = re.sub(r"]\s*\{", "], {", text)
    text = re.sub(r",\s*]", "]", text)
    text = re.sub(r",\s*}", "}", text)

    return text


def calculate_coverage_score(cases, docs_dict=None):
    """真实覆盖率计算"""
    if not docs_dict:
        return 0

    doc_index = {}
    for name, content in docs_dict.items():
        doc_index[name] = (name + "\n" + content).lower()

    total_doc_names = set(docs_dict.keys())
    if not total_doc_names: return 0

    covered_docs = set()
    target_api_names = set()

    for case in cases:
        if "steps" in case:
            for step in case["steps"]:
                if "api_name" in step:
                    target_api_names.add(str(step["api_name"]).strip())
        elif "api_name" in case:
            target_api_names.add(str(case["api_name"]).strip())

    for api_target in target_api_names:
        if not api_target: continue
        target_lower = api_target.lower()

        for doc_name, full_content in doc_index.items():
            if target_lower in full_content:
                covered_docs.add(doc_name)

    score = (len(covered_docs) / len(total_doc_names)) * 100
    return int(score) if score <= 100 else 100


# ================= 4. 数据工厂 (DataFactory) =================
class DataFactory:
    """智能数据工厂"""

    @staticmethod
    def generate(key_name, data_type="string", **kwargs):
        # 1. Key 归一化
        raw_key = str(key_name).lower()
        key = raw_key.replace("_", "")

        raw_msg_type = str(kwargs.get('msg_type', 'text')).lower()
        specific_msg_type = raw_msg_type.replace("_", "")

        # 🚀 优先处理显式传递的环境变量
        explicit_env_key = kwargs.get('env_key')
        if explicit_env_key:
            env_val = os.environ.get(str(explicit_env_key))
            if env_val: return env_val

        # 🚀 智能环境嗅探
        auto_env = get_app_context(key_name)
        if auto_env: return auto_env

        # ID 类参数的特殊嗅探
        if any(k in key for k in ["receiveid", "chatid", "openid", "userid"]):
            id_type_param = str(kwargs.get('receive_id_type', 'open_id')).lower()
            if "chat" in key or "chat" in id_type_param:
                real_chat_id = os.environ.get("TEST_CHAT_ID")
                if real_chat_id: return real_chat_id
            else:
                real_user_id = os.environ.get("TEST_USER_ID")
                if real_user_id: return real_user_id

        # ================= Mock 逻辑 =================
        if "uuid" in key or "traceid" in key:
            return str(uuid.uuid4())

        if "time" in key:
            return int(time.time() * 1000)

        # 🌟 增强：针对 content 的复杂结构生成
        if "content" in key:
            # 卡片消息
            if "interactive" in specific_msg_type or "card" in key:
                card = {
                    "config": {"wide_screen_mode": True},
                    "header": {"title": {"tag": "plain_text", "content": "AutoQA Test"}, "template": "blue"},
                    "elements": [
                        {"tag": "div", "text": {"content": "**ID**: " + str(uuid.uuid4()), "tag": "lark_md"}}
                    ]
                }
                return json.dumps(card, ensure_ascii=False)

            # 富文本消息
            if "post" in specific_msg_type:
                post = {
                    "zh_cn": {
                        "title": "Test",
                        "content": [[{"tag": "text", "text": "AutoQA Generated Content"}]]
                    }
                }
                # 注意：飞书 Open API 发送 post 时，content 字段内部不需要再包一层 "post" key
                return json.dumps(post, ensure_ascii=False)

            # 图片消息
            if "image" in specific_msg_type:
                return json.dumps({"image_key": os.environ.get("TEST_IMAGE_KEY", "mock_img_key")}, ensure_ascii=False)

            # 默认文本
            return json.dumps({"text": f"AutoQA: {fake.sentence()}"}, ensure_ascii=False)

        # 其他兜底
        if "receiveid" in key:
            real_id = os.environ.get("TEST_USER_ID") or \
                      os.environ.get("USER_OPEN_ID") or \
                      os.environ.get("GROUP_CHAT_ID") or \
                      os.environ.get("TEST_CHAT_ID")
            if real_id: return real_id

            return "ou_" + uuid.uuid4().hex[:10]

        if "email" in key: return fake.email()
        if "name" in key: return fake.name()
        if "timestamp" in key: return int(time.time() * 1000)

        return f"Auto_{raw_key}_{int(time.time())}"