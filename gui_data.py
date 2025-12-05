import re
import json
from typing import List, Dict, Any
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox


# ========== Markdown 解析相关函数 ==========

def extract_title_and_desc(md: str):
    """从 Markdown 顶部提取标题和简介（# 标题 + 段落）"""
    lines = md.splitlines()
    title = ""
    desc_lines = []
    in_desc = False
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            in_desc = True
            continue
        if in_desc:
            if line.startswith("## "):
                break
            if line.strip() == "":
                continue
            desc_lines.append(line.strip())
    desc = " ".join(desc_lines)
    return title, desc


def extract_basic_info(md: str):
    """提取 HTTP URL 和 HTTP Method 两项基础信息"""
    url = None
    method = None

    url_match = re.search(r"HTTP URL\s*\|\s*(.+)", md)
    method_match = re.search(r"HTTP Method\s*\|\s*(.+)", md)

    if url_match:
        url = url_match.group(1).strip()
    if method_match:
        method = method_match.group(1).strip().upper()

    return url, method


def parse_table_block(lines: List[str], start_idx: int) -> (List[Dict[str, Any]], int):
    """从 Markdown 某一行开始，解析一个表格块为 rows 列表"""
    header_line = lines[start_idx].strip()
    headers = [h.strip() for h in header_line.split("|") if h.strip()]

    rows = []
    i = start_idx + 2  # 跳过分隔行 ---|---
    while i < len(lines):
        line = lines[i]
        if line.strip() == "" or line.startswith("### ") or line.startswith("## "):
            break
        if "|" not in line:
            break

        cols = [c.strip() for c in line.split("|")]
        if len(cols) < len(headers):
            i += 1
            continue

        row = {}
        header_idx = 0
        for c in cols:
            if c == "":
                continue
            if header_idx >= len(headers):
                break
            row[headers[header_idx]] = c
            header_idx += 1

        if row:
            rows.append(row)
        i += 1

    return rows, i


def extract_section_table(md: str, section_title: str) -> List[Dict[str, Any]]:
    """根据标题（### 请求头 / 查询参数 / 请求体）提取对应表格"""
    lines = md.splitlines()
    rows: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"### {section_title}"):
            j = idx + 1
            # 找到第一行带 | 的表头
            while j < len(lines) and "|" not in lines[j]:
                j += 1
            if j >= len(lines):
                break
            rows, _ = parse_table_block(lines, j)
            break
    return rows


def extract_code_block_after(md: str, marker: str, lang: str = "json") -> str:
    """提取某个 marker（例如 ### 请求体示例）后第一段 ```json``` 代码块"""
    pattern = rf"{marker}[\s\S]*?```{lang}\s*([\s\S]*?)```"
    m = re.search(pattern, md)
    if not m:
        return ""
    return m.group(1).strip()


def safe_parse_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def build_api_meta_from_md(md: str) -> Dict[str, Any]:
    """综合解析 Markdown，形成统一的 api_meta 结构"""
    title, desc = extract_title_and_desc(md)
    url, method = extract_basic_info(md)

    headers_table = extract_section_table(md, "请求头")
    query_table = extract_section_table(md, "查询参数")
    body_table = extract_section_table(md, "请求体")

    req_body_example_text = extract_code_block_after(md, r"### 请求体示例", "json")
    resp_example_text = extract_code_block_after(md, r"### 响应体示例", "json")

    req_body_example = safe_parse_json(req_body_example_text)
    resp_example = safe_parse_json(resp_example_text)

    api_meta = {
        "name": title,
        "description": desc,
        "method": method,
        "url": url,
        "headers_table": headers_table,
        "query_params_table": query_table,
        "body_params_table": body_table,
        "request_body_example_raw": req_body_example_text,
        "request_body_example_json": req_body_example,
        "response_example_raw": resp_example_text,
        "response_example_json": resp_example,
    }
    return api_meta


# ========== 通用字段驱动映射逻辑（不写死 action） ==========

def guess_resource_name(url: str) -> str:
    """
    根据 URL 推一个资源名，用于 case_name，比如:
    https://open.feishu.cn/open-apis/im/v1/messages/:message_id -> messages
    """
    if not url:
        return "api"
    clean = url.replace("https://", "").replace("http://", "")
    parts = clean.split("/")
    # 查找 v1 / v2 后面的那一段
    for i, p in enumerate(parts):
        if re.match(r"v\d+", p):
            if i + 1 < len(parts):
                return parts[i + 1] or "api"
    return parts[-1] or "api"


def build_headers_from_meta(api_meta: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, str]:
    """只负责 Authorization 和 Content-Type 的通用构造"""
    headers: Dict[str, str] = {}

    # 1) Authorization：从 GUI 拿，自动补 Bearer
    token_raw = (cfg.get("authorization") or "").strip()
    if token_raw:
        if not token_raw.lower().startswith("bearer "):
            token = f"Bearer {token_raw}"
        else:
            token = token_raw
        headers["Authorization"] = token

    method = (api_meta.get("method") or "GET").upper()
    has_body_method = method in {"POST", "PUT", "PATCH"}

    headers_table = api_meta.get("headers_table") or []
    for row in headers_table:
        name = row.get("名称") or row.get("name") or ""
        if not name:
            continue
        lower = name.lower()
        if lower == "authorization":
            # 文档里示例的 token 不要用，优先用 GUI 里的
            continue
        if lower == "content-type":
            # 统一走 JSON
            headers["Content-Type"] = "application/json; charset=utf-8"

    if has_body_method and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json; charset=utf-8"

    return headers


def build_params_from_meta(api_meta: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据「查询参数」表格 + 字段名，构造 params：
    - receive_id_type -> chat_id
    - container_id_type -> chat
    - user_id_type -> open_id
    其他参数用 raw_data:xxx 占位，高级映射可覆盖。
    """
    params: Dict[str, Any] = {}
    adv: Dict[str, str] = cfg.get("advanced_map", {}) or {}
    query_table = api_meta.get("query_params_table") or []

    for row in query_table:
        name = row.get("名称") or row.get("name") or ""
        if not name:
            continue
        key = name.strip()

        # 高级映射优先
        if key in adv:
            params[key] = adv[key]
            continue

        key_lower = key.lower()

        if key_lower == "receive_id_type":
            params[key] = "chat_id"
        elif key_lower == "container_id_type":
            params[key] = "chat"
        elif key_lower == "user_id_type":
            params[key] = "open_id"
        else:
            params[key] = f"raw_data:{key}"

    return params


def build_body_from_meta(api_meta: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据「请求体」表格 + 示例 JSON + 字段名，构造 body。
    不依赖具体接口，只基于字段名做通用推断。
    """
    body: Dict[str, Any] = {}
    adv: Dict[str, str] = cfg.get("advanced_map", {}) or {}
    default_chat = cfg.get("default_chat_id") or "oc_raw_data:chat"
    default_user = cfg.get("default_user_id") or "ou_raw_data:user"

    body_table = api_meta.get("body_params_table") or []
    example_json = api_meta.get("request_body_example_json") or {}

    for row in body_table:
        name = row.get("名称") or row.get("name") or ""
        if not name:
            continue
        key = name.strip()
        key_lower = key.lower()

        # 高级映射优先
        if key in adv:
            body[key] = adv[key]
            continue

        # 常见字段的通用规则
        if key_lower == "receive_id":
            body[key] = default_chat
        elif key_lower == "msg_type":
            body[key] = "text"
        elif key_lower == "content":
            body[key] = "raw_data:content"
        elif key_lower == "uuid":
            body[key] = "GENERATE_UUID"
        elif key_lower == "user_id":
            body[key] = default_user
        else:
            # 如果示例 JSON 里有，就用示例；否则占位
            if isinstance(example_json, dict) and key in example_json:
                body[key] = example_json[key]
            else:
                body[key] = f"raw_data:{key}"

    return body


def build_case_from_api_meta(api_meta: Dict[str, Any], cfg: Dict[str, Any], seq: int) -> Dict[str, Any]:
    """
    核心汇总：把解析出的 api_meta + 全局配置，转成 linker 需要的 data.json 单条接口结构。
    不写死“发送/编辑/转发”等业务动作。
    """
    url = api_meta.get("url") or ""
    method = (api_meta.get("method") or "GET").upper()
    resource = guess_resource_name(url)
    index_str = f"{seq:02d}"

    case_name = f"{method.lower()}_{resource}_{index_str}"

    desc_from_doc = api_meta.get("description") or ""
    if desc_from_doc:
        description = f"[自动化] {desc_from_doc}"
    else:
        description = f"[自动化] {method} {url}"

    headers = build_headers_from_meta(api_meta, cfg)
    params = build_params_from_meta(api_meta, cfg)
    body = build_body_from_meta(api_meta, cfg)

    case: Dict[str, Any] = {
        "case_name": case_name,
        "description": description,
        "url": url,
        "method": method,
        "headers": headers,
        "params": params
    }
    if body:
        case["body"] = body

    return case


# ========== 全局真实值后处理：chat_id / user_id 智能填充 ==========

def apply_global_defaults_to_case(case: Dict[str, Any],
                                 default_chat_id: str,
                                 default_user_id: str) -> Dict[str, Any]:
    """
    使用 GUI 顶部的 Default Chat ID / Default User ID
    对单个用例做一次“收尾处理”，保证 data.json 里是真实可跑的值。

    规则（完全基于字段名，不看 URL）：
    1) 如果 params.container_id_type in {chat, chat_id, group_chat}：
       - params.container_id 是 raw_data:xxx 或空，则用 default_chat_id
    2) 如果 params.receive_id_type in {chat, chat_id}：
       - body.receive_id 是 raw_data:xxx 或空，则用 default_chat_id
    3) 所有 key 里包含 user_id 且值为 raw_data:xxx 的字段，用 default_user_id
    """
    params = case.setdefault("params", {})
    body = case.setdefault("body", {})

    default_chat_id = (default_chat_id or "").strip()
    default_user_id = (default_user_id or "").strip()

    # --- 1. chat 相关 container_id ---
    cid_type = str(params.get("container_id_type", "")).lower()
    if default_chat_id and cid_type in ("chat", "chat_id", "group_chat"):
        cid_val = params.get("container_id")
        if not cid_val or (isinstance(cid_val, str) and cid_val.startswith("raw_data:")):
            params["container_id"] = default_chat_id

    # --- 2. chat 相关 receive_id ---
    rid_type = str(params.get("receive_id_type", "")).lower()
    if default_chat_id and rid_type in ("chat", "chat_id"):
        rid_val = body.get("receive_id")
        if not rid_val or (isinstance(rid_val, str) and rid_val.startswith("raw_data:")):
            body["receive_id"] = default_chat_id

    # --- 3. user 相关：所有 *user_id* 字段 ---
    if default_user_id:
        for d in (params, body):
            for k, v in list(d.items()):
                key_lower = k.lower()
                if "user_id" in key_lower and isinstance(v, str) and v.startswith("raw_data:"):
                    d[k] = default_user_id

    return case


# ========== GUI 部分 ==========

class MdGuiApp:
    def __init__(self, root):
        self.root = root
        root.title("飞书 Markdown 接口文档 → data.json 生成器（字段驱动·通用版）")

        self.case_list: List[Dict[str, Any]] = []
        self.case_counter: int = 1  # 用来给用例编号

        # 顶部配置区域（全局真实值）
        cfg_frame = tk.LabelFrame(root, text="全局配置（真实值）")
        cfg_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Authorization
        tk.Label(cfg_frame, text="Authorization:").grid(row=0, column=0, sticky="w")
        self.entry_auth = tk.Entry(cfg_frame, width=60)
        self.entry_auth.grid(row=0, column=1, sticky="w", padx=5, columnspan=3)

        # Default Chat ID
        tk.Label(cfg_frame, text="Default Chat ID:").grid(row=1, column=0, sticky="w")
        self.entry_chat = tk.Entry(cfg_frame, width=40)
        self.entry_chat.insert(0, "oc_你的群聊ID")
        self.entry_chat.grid(row=1, column=1, sticky="w", padx=5)

        # Default User ID
        tk.Label(cfg_frame, text="Default User ID:").grid(row=1, column=2, sticky="w")
        self.entry_user = tk.Entry(cfg_frame, width=30)
        self.entry_user.insert(0, "ou_你的用户ID")
        self.entry_user.grid(row=1, column=3, sticky="w", padx=5)

        # 高级映射
        adv_frame = tk.LabelFrame(root, text="高级映射（可选，key=value，每行一条；用于覆盖默认规则）")
        adv_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.adv_text = scrolledtext.ScrolledText(adv_frame, wrap=tk.WORD, width=120, height=5)
        self.adv_text.insert(
            tk.END,
            "# 示例：\n"
            "# receive_id_type=chat_id\n"
            "# receive_id=oc_xxx\n"
            "# container_id_type=chat\n"
            "# container_id=oc_xxx\n"
            "# user_id_type=open_id\n"
        )
        self.adv_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ========= 中间区域：左右两个白框 =========
        center_frame = tk.Frame(root)
        center_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧：Markdown 输入
        left_frame = tk.Frame(center_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(left_frame, text="粘贴飞书『复制页面』内容（每个接口一粘）：").pack(anchor="w")
        self.md_text = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, width=70, height=30)
        self.md_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 右侧：JSON 输出（所有用例）
        right_frame = tk.Frame(center_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="当前用例列表（data.json 内容预览）：").pack(anchor="w")
        self.json_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, width=70, height=30)
        self.json_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ========= 底部按钮区域：紧贴两个白框下方，居中 =========
        btn_frame = tk.Frame(root)
        btn_frame.pack(side=tk.TOP, pady=5)  # 注意这里用 TOP，不用 BOTTOM

        tk.Button(btn_frame, text="➕ 添加当前接口为一个用例",
                  command=self.on_add_case).pack(side=tk.LEFT, padx=10, pady=5)
        tk.Button(btn_frame, text="🧹 清空用例列表",
                  command=self.on_clear_cases).pack(side=tk.LEFT, padx=10, pady=5)
        tk.Button(btn_frame, text="💾 保存为 data.json",
                  command=self.on_save).pack(side=tk.LEFT, padx=10, pady=5)


    # --------- 配置读取 ---------
    def parse_advanced_map(self) -> Dict[str, str]:
        text = self.adv_text.get("1.0", tk.END)
        mapping: Dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            mapping[k.strip()] = v.strip()
        return mapping

    def get_global_cfg(self) -> Dict[str, Any]:
        return {
            "authorization": self.entry_auth.get().strip(),
            "default_chat_id": self.entry_chat.get().strip(),
            "default_user_id": self.entry_user.get().strip(),
            "advanced_map": self.parse_advanced_map(),
        }

    # --------- GUI 事件 ---------
    def on_add_case(self):
        md = self.md_text.get("1.0", tk.END)
        if not md.strip():
            messagebox.showwarning("提示", "请先粘贴 Markdown 文本。")
            return

        try:
            api_meta = build_api_meta_from_md(md)
            cfg = self.get_global_cfg()
            case = build_case_from_api_meta(api_meta, cfg, self.case_counter)

            # 关键一步：应用全局默认 chat_id / user_id
            case = apply_global_defaults_to_case(
                case,
                cfg.get("default_chat_id"),
                cfg.get("default_user_id"),
            )

            self.case_list.append(case)
            self.case_counter += 1

            # 更新右侧预览
            self.refresh_json_preview()

            messagebox.showinfo("成功", f"已添加用例：{case['case_name']}")
        except Exception as e:
            messagebox.showerror("错误", f"解析或添加失败：{e}")

    def refresh_json_preview(self):
        json_str = json.dumps(self.case_list, ensure_ascii=False, indent=2)
        self.json_text.delete("1.0", tk.END)
        self.json_text.insert(tk.END, json_str)

    def on_clear_cases(self):
        if messagebox.askyesno("确认", "确定要清空所有已添加的用例吗？"):
            self.case_list = []
            self.case_counter = 1
            self.refresh_json_preview()

    def on_save(self):
        if not self.case_list:
            messagebox.showwarning("提示", "当前用例列表为空，无法保存。请先添加一些用例。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="data.json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        # 再保险一次：保存前再按当前全局配置跑一遍默认填充
        cfg = self.get_global_cfg()
        final_cases = [
            apply_global_defaults_to_case(
                json.loads(json.dumps(c)),  # 深拷贝，避免直接改内存
                cfg.get("default_chat_id"),
                cfg.get("default_user_id"),
            )
            for c in self.case_list
        ]

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(final_cases, f, ensure_ascii=False, indent=2)

        messagebox.showinfo("成功", f"已保存到：{file_path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MdGuiApp(root)
    root.mainloop()
