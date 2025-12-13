# app.py
import streamlit as st
import pandas as pd
import time
import json
import os
from llm_bridge import LLMBridge
from test_runner import PytestRunner
from report_engine import EnhancedVisualReportGenerator


# 加载自定义CSS
def load_css():
    css_path = "style.css"
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        # 内联样式作为备份
        st.markdown("""
        <style>
        .metric-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1.5rem; border-radius: 12px; color: white; text-align: center; }
        .status-badge-pass { background-color: #d4edda; color: #155724; padding: 4px 12px; border-radius: 20px; display: inline-block; }
        .status-badge-fail { background-color: #f8d7da; color: #721c24; padding: 4px 12px; border-radius: 20px; display: inline-block; }
        .status-badge-skip { background-color: #fff3cd; color: #856404; padding: 4px 12px; border-radius: 20px; display: inline-block; }
        .execution-card { background: #f8f9fa; padding: 1.2rem; border-radius: 10px; border-left: 4px solid #667eea; margin: 12px 0; }
        </style>
        """, unsafe_allow_html=True)


def get_status_badge(status, show_label=True):
    """返回带颜色的状态徽章HTML"""
    status_config = {
        "PASS": {
            "emoji": "🟢",
            "class": "status-badge-pass",
            "label": "通过",
            "card_class": "pass"
        },
        "FAIL": {
            "emoji": "🔴",
            "class": "status-badge-fail",
            "label": "失败",
            "card_class": "fail"
        },
        "SKIP": {
            "emoji": "🟡",
            "class": "status-badge-skip",
            "label": "跳过",
            "card_class": "skip"
        },
        "PASS (Healed)": {
            "emoji": "🟣",
            "class": "status-badge-healed",
            "label": "修复后通过",
            "card_class": "healed"
        },
        "RUNNING": {
            "emoji": "🔄",
            "class": "status-badge-running",
            "label": "运行中",
            "card_class": "running"
        }
    }

    config = status_config.get(status, {
        "emoji": "⚪",
        "class": "",
        "label": status,
        "card_class": ""
    })

    if show_label:
        return (
            f'<span class="{config["class"]}">{config["emoji"]} {config["label"]}</span>',
            config["card_class"]
        )
    else:
        return config["emoji"], config["card_class"]


# 设置页面配置
st.set_page_config(
    page_title="AutoQA Benchmarking",
    layout="wide",
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

# 加载CSS
load_css()

# ================= 侧边栏 =================
with st.sidebar:
    st.markdown('<div class="sidebar-header">', unsafe_allow_html=True)
    st.title("🎛️ 智能控制台")
    st.markdown('</div>', unsafe_allow_html=True)

    api_base = st.text_input("API Base", value="[https://api.deepseek.com](https://api.deepseek.com)")
    model_name = st.text_input("Model", value="deepseek-chat")
    api_key = st.text_input("API Key", type="password")
    target_host = st.text_input("目标 Host", value="[https://open.feishu.cn](https://open.feishu.cn)")

    st.markdown("---")
    st.subheader("📏 评估基准 (仅用于评分)")
    st.info("在此上传人工设计的测试用例 JSON (Golden Set)。")
    human_benchmark_file = st.file_uploader("上传人工 Golden Set", type=["json"])

    human_benchmark_data = []
    if human_benchmark_file:
        try:
            human_benchmark_data = json.load(human_benchmark_file)
            st.success(f"✅ 已加载 {len(human_benchmark_data)} 条基准用例")
        except:
            st.error("JSON 格式错误")

    st.markdown("---")
    st.subheader("🌍 环境变量")
    if "env_data" not in st.session_state:
        st.session_state.env_data = [{"Key": "API_TOKEN", "Value": ""}]

    edited_df = st.data_editor(
        st.session_state.env_data,
        column_config={"Key": "变量名", "Value": "值"},
        num_rows="dynamic",
        key="env_editor"
    )
    custom_env_vars = {}
    for row in edited_df:
        k = row.get("Key")
        v = row.get("Value")
        if k:
            custom_env_vars[str(k).strip()] = str(v).strip()

# ================= 主逻辑 =================

if "test_plan" not in st.session_state: st.session_state.test_plan = None
if "execution_results" not in st.session_state: st.session_state.execution_results = []
if "report_data" not in st.session_state: st.session_state.report_data = None
if "docs_cache" not in st.session_state: st.session_state.docs_cache = {}

st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("⚖️ AutoQA: 人机对齐评测平台")
st.markdown('</div>', unsafe_allow_html=True)

# --- 1. 文档接入 ---
st.header("1. 📄 接入 API 文档 (AI 的唯一输入)")
uploaded_files = st.file_uploader("上传 Markdown 接口文档 (支持多选)", type=["md", "txt"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.read().decode("utf-8")
        st.session_state.docs_cache[uploaded_file.name] = content

    st.success(f"✅ 已加载 {len(st.session_state.docs_cache)} 个接口文档")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🧠 分析文档并生成策略", type="primary", use_container_width=True):
            if not api_key:
                st.error("请配置 API Key")
            else:
                with st.spinner("AI 正在分析血缘关系，分步构建策略..."):
                    llm = LLMBridge(api_key, api_base, model_name)
                    plan = llm.analyze_topology(st.session_state.docs_cache)

                    if "error" in plan:
                        st.error(plan['error'])
                    else:
                        st.session_state.test_plan = plan
                        st.session_state.report_data = None

                        # 自动提取必填项并回填到侧边栏
                        env_config = plan.get('env_vars_config', [])
                        current_keys = [row['Key'] for row in st.session_state.env_data]
                        added_count = 0

                        for item in env_config:
                            key = item['key']
                            if key not in current_keys:
                                st.session_state.env_data.append({"Key": key, "Value": ""})
                                added_count += 1

                        if added_count > 0:
                            st.toast(f"✅ 策略生成完毕！已自动添加 {added_count} 个必填环境变量，请在左侧填写。", icon="📝")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.success("✅ 策略生成完毕")

    with col2:
        if st.session_state.docs_cache:
            with st.expander("📚 已加载文档列表", expanded=False):
                for doc_name in st.session_state.docs_cache.keys():
                    st.markdown(f"• {doc_name}")

# --- 2. 执行与评估 ---
if st.session_state.test_plan:
    plan = st.session_state.test_plan

    # 展示测试计划详情
    scenarios = plan.get('scenarios', [])
    singles = plan.get('single_api_cases', [])
    total_planned = len(scenarios) + len(singles)

    st.info(f"📋 AI 规划了 {total_planned} 个测试场景。详情如下：")

    # 展平数据用于显示
    display_data = []
    for s in scenarios:
        display_data.append({
            "类型": "🔗 链路场景",
            "ID": s.get('name', 'N/A'),
            "描述": s.get('description', '')
        })
    for s in singles:
        display_data.append({
            "类型": "🧪 单点测试",
            "ID": s.get('id', 'N/A'),
            "描述": s.get('description', '')
        })

    # 构建 DataFrame 方便展示和下载
    df_display = pd.DataFrame(display_data)

    with st.expander("👁️ 查看详细测试计划列表 (点击展开)", expanded=True):
        # 添加样式
        styled_df = df_display.style.apply(
            lambda x: ['background: #f0f7ff' if x.name % 2 == 0 else '' for _ in x],
            axis=1
        )
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # 🌟🌟🌟 新增：下载测试计划按钮 🌟🌟🌟
    csv_plan = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 下载测试计划 (CSV)",
        data=csv_plan,
        file_name=f"test_plan_{int(time.time())}.csv",
        mime="text/csv",
        key="btn_download_plan_csv"
    )

    st.header("2. 🚀 自动化执行 & 盲测对比")
    tab_exec, tab_report = st.tabs(["⚡ 执行控制台", "📊 评测报告"])

    # === Tab 1: 执行 ===
    with tab_exec:
        st.markdown("""
        <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin-bottom: 1.5rem;">
            <h4 style="margin: 0 0 10px 0;">执行说明</h4>
            <p style="margin: 0; font-size: 0.9rem; color: #666;">
                点击下方按钮开始盲测执行。AI将生成测试代码并自动执行，您可以实时查看执行进度和结果。
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("▶️ 启动生成与执行 (盲测模式)", type="primary", use_container_width=True):
            llm = LLMBridge(api_key, api_base, model_name)
            runner = PytestRunner()
            st.session_state.execution_results = []

            full_suite = scenarios + singles
            total = len(full_suite)

            # 创建进度显示区域
            progress_col1, progress_col2, progress_col3 = st.columns(3)
            with progress_col1:
                progress_bar = st.progress(0, text="总进度")
            with progress_col2:
                success_counter = st.metric("✅ 成功", 0)
            with progress_col3:
                fail_counter = st.metric("❌ 失败", 0)

            # 日志容器
            logs_container = st.container()

            for idx, item in enumerate(full_suite):
                case_id = item.get('name') or item.get('id')
                desc = item.get('description', '')

                with logs_container:
                    with st.status(f"处理: {case_id}...", expanded=False) as status:
                        # 1. 代码生成
                        t0 = time.time()
                        code = llm.generate_scenario_code(item, st.session_state.docs_cache, target_host)
                        t1 = time.time()
                        gen_time = t1 - t0

                        st.code(code, language='python')

                        # 2. 静态依赖检查
                        import re

                        required_vars = set(re.findall(r'get_app_context\s*\(\s*["\']([^"\']+)["\']', code))
                        existing_keys = set(k.lower() for k in custom_env_vars.keys())
                        missing_vars = [v for v in required_vars if
                                        v.lower() not in existing_keys and v.lower() not in ['api_token']]

                        if missing_vars:
                            st.warning(f"⚠️ 检测到代码依赖以下未配置变量，可能导致运行失败: {missing_vars}")

                        # 3. 执行与智能自愈
                        MAX_RETRIES = 3
                        current_try = 0

                        # 初次执行
                        is_pass, log = runner.run_single_case_stream(case_id, code, custom_env_vars)

                        # 自愈循环
                        while not is_pass and "Skipping" not in log and current_try < MAX_RETRIES:
                            if "ValueError" in log and "环境变量" in log:
                                log += "\n[System] 🛑 停止自愈：检测到核心环境变量缺失。请在左侧侧边栏补充配置。"
                                status.update(state="error", label=f"❌ {case_id} 失败：缺少必要参数")
                                break

                            if "401" in log or "403" in log:
                                log += "\n[System] 🛑 停止自愈：鉴权失败 (401/403)，请检查 API Key 是否有效。"
                                break

                            current_try += 1
                            status.update(label=f"🚑 自愈介入中 ({current_try}/{MAX_RETRIES}) - 尝试修复代码...",
                                          state="running")

                            try:
                                code = llm.heal_code(code, log)
                                is_pass, log = runner.run_single_case_stream(case_id, code, custom_env_vars)
                            except Exception as e:
                                log += f"\n[System Error] 自愈服务异常: {str(e)}"
                                break

                        t2 = time.time()
                        exec_time = t2 - t1

                        # 4. 结果记录
                        status_str = "PASS" if is_pass else "FAIL"
                        if is_pass and current_try > 0:
                            status_str = "PASS (Healed)"
                        elif "Skipping" in log:
                            status_str = "SKIP"

                        final_state = "complete" if is_pass else "error"
                        status.update(label=f"{status_str}: {case_id}", state=final_state)

                        st.session_state.execution_results.append({
                            "id": case_id,
                            "status": status_str,
                            "log": log,
                            "desc": desc,
                            "gen_time": round(gen_time, 2),
                            "exec_time": round(exec_time, 2)
                        })

                # 更新进度和计数器
                progress = (idx + 1) / total
                progress_bar.progress(progress, text=f"处理中: {idx + 1}/{total}")

                # 更新计数
                success_count = len(
                    [r for r in st.session_state.execution_results if r['status'] in ['PASS', 'PASS (Healed)']])
                fail_count = len([r for r in st.session_state.execution_results if r['status'] == 'FAIL'])
                success_counter.metric("✅ 成功", success_count)
                fail_counter.metric("❌ 失败", fail_count)

            # 执行完成
            st.success("🎉 测试执行完毕！")

            # 显示执行摘要
            with st.expander("📊 执行摘要", expanded=True):
                total_executed = len(st.session_state.execution_results)
                pass_count = len(
                    [r for r in st.session_state.execution_results if r['status'] in ['PASS', 'PASS (Healed)']])
                fail_count = len([r for r in st.session_state.execution_results if r['status'] == 'FAIL'])
                skip_count = len([r for r in st.session_state.execution_results if r['status'] == 'SKIP'])

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("总计", total_executed)
                with col2:
                    st.metric("通过", pass_count)
                with col3:
                    st.metric("失败", fail_count)
                with col4:
                    st.metric("跳过", skip_count)

            # 生成报告
            generator = EnhancedVisualReportGenerator()
            st.session_state.report_data = generator.generate_execution_report(
                st.session_state.execution_results,
                st.session_state.test_plan,
                human_benchmark=human_benchmark_data
            )

            st.info("📋 报告已生成，请点击上方 '📊 评测报告' 标签页查看详细分析")

    # === Tab 2: 报告 ===
    with tab_report:
        if st.session_state.report_data:
            generator = EnhancedVisualReportGenerator()
            generator.display_report_in_streamlit(st.session_state.report_data)
        else:
            st.info("👈 请先在 '执行控制台' 运行测试")

            # 如果有历史数据，显示历史执行结果
            if st.session_state.execution_results:
                st.subheader("📋 历史执行结果")

                for result in st.session_state.execution_results:
                    badge_html, card_class = get_status_badge(result['status'])

                    st.markdown(f"""
                    <div class="execution-card {card_class}">
                        {badge_html}
                        <strong>{result['id']}</strong>
                        <small>{result['desc']}</small>
                        <div class="meta">
                            <span>生成: {result['gen_time']}s</span>
                            <span>执行: {result['exec_time']}s</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# --- 初始状态显示 ---
else:
    if not st.session_state.docs_cache:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   padding: 3rem; border-radius: 15px; color: white; text-align: center; margin: 2rem 0;">
            <h1 style="font-size: 2.5rem; margin-bottom: 1rem;">🚀 欢迎使用 AutoQA</h1>
            <p style="font-size: 1.2rem; opacity: 0.9;">
                让AI测试更智能、更可靠
            </p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### 📄 上传文档")
            st.info("上传您的API文档，AI将自动分析")
        with col2:
            st.markdown("### 🤖 AI分析")
            st.info("智能识别接口关系，生成测试策略")
        with col3:
            st.markdown("### ⚡ 自动执行")
            st.info("生成并执行测试代码，实时反馈结果")

        st.markdown("---")

        st.markdown("### 🎯 快速开始")
        st.write("1. 在左侧配置API参数")
        st.write("2. 上传API文档（Markdown格式）")
        st.write("3. 点击'分析文档并生成策略'")
        st.write("4. 查看AI生成的测试计划并执行")