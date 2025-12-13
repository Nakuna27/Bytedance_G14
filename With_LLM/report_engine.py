# report_engine.py - 集成增强版可视化功能
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from typing import Dict, List, Any, Optional
import re
import numpy as np
import json
import os

# 尝试导入 jieba，如果没有则降级使用 split
try:
    import jieba
except ImportError:
    jieba = None


class EnhancedVisualReportGenerator:
    """增强版可视化报告生成器 (集成可视化增强功能)"""

    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.colors = {
            'PASS': '#2E8B57',  # 绿色
            'FAIL': '#DC143C',  # 红色
            'SKIP': '#FF8C00',  # 橙色
            'INFO': '#1E90FF',  # 蓝色
            'WARNING': '#FFD700',  # 金色
            'PASS (Healed)': '#9f7aea'  # 紫色（治愈的用例）
        }

    def _load_css_styles(self):
        """加载自定义CSS样式"""
        st.markdown("""
        <style>
        .report-header {
            padding-bottom: 1.5rem;
            border-bottom: 2px solid #eaeaea;
            margin-bottom: 2rem;
        }
        .insight-card {
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 10px;
            border-left: 4px solid #667eea;
            margin: 1rem 0;
        }
        .missed-case {
            background: #fff5f5;
            padding: 0.8rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            border-left: 3px solid #f56565;
        }
        .extra-case-pass {
            background: #f0fff4;
            padding: 0.8rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            border-left: 3px solid #48bb78;
        }
        .extra-case-fail {
            background: #fff5f5;
            padding: 0.8rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            border-left: 3px solid #f56565;
        }
        .metric-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            text-align: center;
        }
        .metric-card-red {
            background: linear-gradient(135deg, #fed7d7 0%, #fff5f5 100%);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #feb2b2;
            text-align: center;
        }
        .metric-card-green {
            background: linear-gradient(135deg, #c6f6d5 0%, #f0fff4 100%);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #9ae6b4;
            text-align: center;
        }
        .metric-card-blue {
            background: linear-gradient(135deg, #bee3f8 0%, #ebf8ff 100%);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #90cdf4;
            text-align: center;
        }
        .metric-card-orange {
            background: linear-gradient(135deg, #feebc8 0%, #fffaf0 100%);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #fbd38d;
            text-align: center;
        }
        .risk-badge {
            display: inline-block;
            padding: 0.25rem 1rem;
            border-radius: 9999px;
            font-weight: bold;
        }
        .risk-low {
            background-color: #c6f6d5;
            color: #276749;
        }
        .risk-medium {
            background-color: #feebc8;
            color: #9c4221;
        }
        .risk-high {
            background-color: #fed7d7;
            color: #c53030;
        }
        .risk-critical {
            background-color: #fff5f5;
            color: #9b2c2c;
            border: 2px solid #f56565;
        }
        .swot-box {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        .strengths-box {
            background-color: #f0fff4;
            border-left: 4px solid #48bb78;
        }
        .weaknesses-box {
            background-color: #fff5f5;
            border-left: 4px solid #f56565;
        }
        .opportunities-box {
            background-color: #ebf8ff;
            border-left: 4px solid #4299e1;
        }
        .threats-box {
            background-color: #fffaf0;
            border-left: 4px solid #ed8936;
        }
        </style>
        """, unsafe_allow_html=True)

    def _tokenize(self, text):
        """简单的分词器，将句子转为关键词集合"""
        text = str(text).lower()
        text = re.sub(r'[^\w\u4e00-\u9fa5]+', ' ', text)

        if jieba:
            return set(jieba.cut(text))
        else:
            return set(text.split())

    def _calculate_similarity(self, text1, text2):
        """计算两个文本的 Jaccard 相似度"""
        s1 = self._tokenize(text1)
        s2 = self._tokenize(text2)

        if not s1 or not s2:
            return 0.0

        intersection = s1.intersection(s2)
        union = s1.union(s2)

        return len(intersection) / len(union)

    def _is_match(self, human_case, ai_case):
        """判定人工用例和AI用例是否匹配"""
        h_api = human_case.get('api_name', '').lower()
        h_desc = human_case.get('description', '').lower()
        h_type = human_case.get('type', '').lower()

        ai_desc = ai_case.get('desc', '').lower()
        ai_id = ai_case.get('id', '').lower()

        # API 范围判定
        api_match = False
        h_keywords = set(re.split(r'[_ ]', h_api))
        ai_keywords = set(re.split(r'[_ ]', ai_id))

        if len(h_keywords.intersection(ai_keywords)) >= 1:
            api_match = True

        if not api_match:
            return False

        # 语义/类型匹配
        similarity = self._calculate_similarity(h_desc, ai_desc)

        if similarity > 0.1 or (h_type in ai_desc):
            return True

        return False

    def _match_human_vs_ai(self, human_cases: List[Dict], ai_results: List[Dict]) -> Dict:
        """核心算法：对比人工基准与AI生成结果"""
        if not human_cases:
            return {}

        # 准备数据
        ai_matched_ids = set()
        matched_human_count = 0
        missed_human_cases = []

        # 双重循环匹配
        for h_case in human_cases:
            is_covered = False

            for ai_res in ai_results:
                if self._is_match(h_case, ai_res):
                    is_covered = True
                    ai_matched_ids.add(ai_res['id'])
                    break

            if is_covered:
                matched_human_count += 1
            else:
                missed_human_cases.append({
                    'api_name': h_case.get('api_name', '未知'),
                    'description': h_case.get('description', '未知描述'),
                    'type': h_case.get('type', '未知类型')
                })

        # 统计增广
        all_ai_ids = set(r['id'] for r in ai_results)
        extra_ids = list(all_ai_ids - ai_matched_ids)

        extra_details = []
        extra_passed = 0
        extra_failed = 0

        ai_lookup = {r['id']: r for r in ai_results}

        for eid in extra_ids:
            res = ai_lookup[eid]
            status = res['status']
            desc = res.get('desc', '')

            if status in ['PASS', 'PASS (Healed)']:
                extra_details.append({
                    'id': eid,
                    'desc': desc,
                    'status': status,
                    'type': 'pass'
                })
                extra_passed += 1
            else:
                extra_details.append({
                    'id': eid,
                    'desc': desc,
                    'status': status,
                    'type': 'fail'
                })
                extra_failed += 1

        # 计算核心指标
        human_total = len(human_cases)
        ai_total = len(ai_results)

        recall = (matched_human_count / human_total * 100) if human_total > 0 else 0
        precision = (matched_human_count / ai_total * 100) if ai_total > 0 else 0

        return {
            "recall": round(recall, 1),
            "precision": round(precision, 1),
            "human_total": human_total,
            "human_covered": matched_human_count,
            "missed_list": missed_human_cases,
            "extra_total": len(extra_ids),
            "extra_valid": extra_passed,
            "extra_invalid": extra_failed,
            "extra_list": extra_details,
            "augmentation_rate": round((extra_passed / len(extra_ids) * 100), 1) if extra_ids else 0
        }

    def _calculate_risk_level(self, pass_rate: float, df: pd.DataFrame = None, test_plan: Dict = None) -> str:
        """计算风险等级"""
        try:
            pass_rate_float = float(pass_rate)
            if pass_rate_float >= 90.0:
                risk = "低风险"
                risk_class = "risk-low"
            elif pass_rate_float >= 70.0:
                risk = "中等风险"
                risk_class = "risk-medium"
            elif pass_rate_float >= 50.0:
                risk = "高风险"
                risk_class = "risk-high"
            else:
                risk = "极高风险"
                risk_class = "risk-critical"
        except:
            risk = "未知风险"
            risk_class = "risk-medium"

        # 核心链路熔断逻辑
        if df is not None and not df.empty and test_plan:
            scenarios = test_plan.get('scenarios', [])
            scenario_ids = [s.get('name') for s in scenarios]
            failed_scenarios = df[(df['id'].isin(scenario_ids)) & (df['status'] == 'FAIL')]
            if not failed_scenarios.empty:
                if risk in ["低风险", "中等风险"]:
                    risk = "高风险 (核心链路阻断)"
                    risk_class = "risk-high"

        return risk, risk_class

    def _create_summary_gauge(self, pass_rate: float) -> go.Figure:
        """创建通过率仪表盘"""
        # 根据通过率设置颜色
        if pass_rate >= 90:
            bar_color = "#48bb78"
        elif pass_rate >= 70:
            bar_color = "#ed8936"
        else:
            bar_color = "#f56565"

        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=pass_rate,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "通过率", 'font': {'size': 20}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': bar_color, 'thickness': 0.3},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 60], 'color': '#fed7d7'},
                    {'range': [60, 80], 'color': '#feebc8'},
                    {'range': [80, 100], 'color': '#c6f6d5'}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))

        fig.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=50, b=20),
            font=dict(size=14)
        )
        return fig

    def _create_status_distribution(self, df: pd.DataFrame) -> go.Figure:
        """创建状态分布图"""
        if df.empty:
            return self._create_empty_chart("状态分布", "无执行数据")

        try:
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['status', 'count']

            colors = {
                'PASS': '#2E8B57',  # 绿色
                'FAIL': '#DC143C',  # 红色
                'SKIP': '#FF8C00',  # 橙色
                'PASS (Healed)': '#9f7aea'  # 紫色
            }

            status_counts['color'] = status_counts['status'].map(
                lambda x: colors.get(x, '#808080')
            )

            fig = go.Figure(data=[go.Pie(
                labels=status_counts['status'],
                values=status_counts['count'],
                marker=dict(colors=status_counts['color']),
                hole=0.3,
                textinfo='label+percent',
                hoverinfo='label+value+percent'
            )])

            fig.update_layout(
                title="测试状态分布",
                height=400,
                showlegend=True,
                margin=dict(l=20, r=20, t=50, b=20)
            )
            return fig
        except Exception as e:
            print(f"创建状态分布图失败: {str(e)}")
            return self._create_empty_chart("状态分布", "图表生成失败")

    def _create_scenario_type_analysis(self, test_plan: Dict) -> go.Figure:
        """创建场景类型分析"""
        if not test_plan:
            return self._create_empty_chart("场景分析", "无测试计划数据")

        try:
            scenarios = test_plan.get('scenarios', [])
            single_cases = test_plan.get('single_api_cases', [])

            categories = ['链路场景', '单点用例', '总计']
            counts = [len(scenarios), len(single_cases), len(scenarios) + len(single_cases)]

            fig = go.Figure(data=[go.Bar(
                x=categories,
                y=counts,
                text=counts,
                textposition='auto',
                marker_color=['#36A2EB', '#FF6384', '#4BC0C0']
            )])

            fig.update_layout(
                title="测试场景类型分布",
                xaxis_title="场景类型",
                yaxis_title="数量",
                height=400,
                margin=dict(l=20, r=20, t=50, b=20)
            )
            return fig
        except Exception as e:
            print(f"创建场景类型分析失败: {str(e)}")
            return self._create_empty_chart("场景分析", "图表生成失败")

    def _create_trend_analysis(self, df: pd.DataFrame) -> go.Figure:
        """创建趋势分析图（简化版）"""
        try:
            # 创建简单的趋势图
            fig = go.Figure()

            # 添加模拟趋势线
            dates = pd.date_range(end=datetime.now(), periods=5, freq='D')
            values = [70, 75, 80, 85, 90]

            fig.add_trace(go.Scatter(
                x=dates,
                y=values,
                mode='lines+markers',
                name='通过率趋势',
                line=dict(color='green', width=3)
            ))

            # 当前值标记
            current_pass_rate = (len(df[df['status'] == 'PASS']) / len(df) * 100) if len(df) > 0 else 0
            fig.add_trace(go.Scatter(
                x=[dates[-1]],
                y=[current_pass_rate],
                mode='markers',
                name='当前值',
                marker=dict(color='red', size=12, symbol='star')
            ))

            fig.update_layout(
                title="测试通过率趋势",
                xaxis_title="日期",
                yaxis_title="通过率 (%)",
                height=300,
                margin=dict(l=20, r=20, t=50, b=20)
            )

            return fig
        except Exception as e:
            print(f"创建趋势分析失败: {str(e)}")
            return self._create_empty_chart("趋势分析", "图表生成失败")

    def _create_failure_pattern(self, df: pd.DataFrame) -> go.Figure:
        """创建失败模式分析图"""
        try:
            if df.empty or len(df[df['status'] == 'FAIL']) == 0:
                return self._create_empty_chart("失败模式", "无失败用例")

            # 简单的失败统计
            fail_count = len(df[df['status'] == 'FAIL'])
            total_count = len(df)
            fail_rate = (fail_count / total_count * 100) if total_count > 0 else 0

            fig = go.Figure(data=[go.Indicator(
                mode="number+gauge",
                value=fail_rate,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "失败率"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "red"},
                    'steps': [
                        {'range': [0, 20], 'color': "lightgreen"},
                        {'range': [20, 50], 'color': "yellow"},
                        {'range': [50, 100], 'color': "red"}
                    ],
                }
            )])

            fig.update_layout(
                height=300,
                margin=dict(l=20, r=20, t=50, b=20)
            )

            return fig
        except Exception as e:
            print(f"创建失败模式分析失败: {str(e)}")
            return self._create_empty_chart("失败模式", "图表生成失败")

    def _create_empty_chart(self, title: str, message: str) -> go.Figure:
        """创建空图表"""
        fig = go.Figure()
        fig.update_layout(
            title=title,
            height=300,
            annotations=[dict(
                text=message,
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=14, color="gray")
            )],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor='rgba(240,240,240,0.8)'
        )
        return fig

    def _generate_detailed_analysis(self, df: pd.DataFrame, test_plan: Dict, metrics: Dict) -> Dict:
        """生成详细分析报告"""
        analysis = {
            'summary': "",
            'strengths': [],
            'weaknesses': [],
            'opportunities': [],
            'threats': [],
            'recommendations': []
        }

        total = metrics['total_tests']
        pass_count = metrics['pass_count']
        fail_count = metrics['fail_count']
        skip_count = metrics['skip_count']
        pass_rate = metrics['pass_rate']

        # 生成总结
        if pass_count == total:
            analysis['summary'] = "🎉 所有测试用例执行通过！"
            analysis['strengths'].append("测试通过率达到100%，质量优秀")
        elif pass_count == 0:
            analysis['summary'] = "😰 所有测试用例执行失败！"
            analysis['weaknesses'].append("测试通过率为0%，需要紧急修复")
        else:
            analysis['summary'] = f"📊 测试完成：{pass_count}/{total} 通过 ({fail_count} 失败, {skip_count} 跳过)"

        # SWOT分析
        if pass_rate >= 90:
            analysis['strengths'].append(f"通过率高达{pass_rate}%，表现优秀")
        elif pass_rate >= 70:
            analysis['strengths'].append(f"通过率{pass_rate}%，表现良好")
        elif pass_rate >= 50:
            analysis['weaknesses'].append(f"通过率{pass_rate}%，需要改进")
        else:
            analysis['weaknesses'].append(f"通过率仅{pass_rate}%，质量堪忧")

        if fail_count > 0:
            analysis['threats'].append(f"有{fail_count}个用例失败，存在风险")
            analysis['recommendations'].append(f"优先修复{fail_count}个失败用例")

        if skip_count > 0:
            analysis['weaknesses'].append(f"有{skip_count}个用例被跳过，环境配置可能有问题")
            analysis['recommendations'].append(f"检查并配置缺失的环境变量")

        if total < 10:
            analysis['opportunities'].append("测试用例数量较少，可以增加更多测试场景")
            analysis['recommendations'].append("增加测试用例覆盖范围")

        return analysis

    def _generate_executive_summary(self, metrics: Dict) -> str:
        """生成执行摘要"""
        summary_parts = []

        summary_parts.append(f"📈 **测试执行完成**，共执行 {metrics['total_tests']} 个用例")
        summary_parts.append(
            f"✅ **通过率**: {metrics['pass_rate']}% ({metrics['pass_count']}/{metrics['total_tests']})")
        summary_parts.append(f"⚠️ **风险等级**: {metrics['risk_level']}")

        if metrics['fail_count'] > 0:
            summary_parts.append(f"❌ **需要关注**: {metrics['fail_count']} 个用例失败")

        if metrics['skip_count'] > 0:
            summary_parts.append(f"⏸️ **环境问题**: {metrics['skip_count']} 个用例被跳过")

        return "  \n".join(summary_parts)

    def generate_execution_report(self, execution_results: List[Dict], test_plan: Dict,
                                  human_benchmark: List[Dict] = None) -> Dict:
        """生成执行报告"""
        if not execution_results:
            return {"error": "无执行结果"}

        try:
            # 转换结果为DataFrame
            df = pd.DataFrame(execution_results)

            # 计算统计数据
            total = len(df)
            pass_count = len(df[df['status'].isin(['PASS', 'PASS (Healed)'])])
            fail_count = len(df[df['status'] == 'FAIL'])
            skip_count = len(df[df['status'] == 'SKIP'])

            # 计算通过率
            pass_rate = (pass_count / total * 100) if total > 0 else 0

            # 计算平均生成耗时
            avg_gen_time = df['gen_time'].mean() if 'gen_time' in df.columns else 0

            # 计算风险等级
            risk_level, risk_class = self._calculate_risk_level(pass_rate, df, test_plan)

            # 人机对齐分析
            benchmark_metrics = {}
            if human_benchmark:
                benchmark_metrics = self._match_human_vs_ai(human_benchmark, execution_results)

            # 生成基础图表
            charts = {
                'summary_gauge': self._create_summary_gauge(pass_rate),
                'status_distribution': self._create_status_distribution(df),
            }

            # 尝试生成其他图表（如果有足够数据）
            try:
                charts['scenario_type_analysis'] = self._create_scenario_type_analysis(test_plan)
                charts['trend_analysis'] = self._create_trend_analysis(df)
                charts['failure_pattern'] = self._create_failure_pattern(df)
            except Exception as e:
                print(f"部分图表生成失败: {str(e)}")

            # 生成指标数据
            metrics = {
                'total_tests': total,
                'pass_count': pass_count,
                'fail_count': fail_count,
                'skip_count': skip_count,
                'pass_rate': round(pass_rate, 1),
                'risk_level': risk_level,
                'risk_class': risk_class,
                'execution_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'avg_gen_time': round(avg_gen_time, 2),
                'benchmark': benchmark_metrics
            }

            # 生成详细分析
            analysis = self._generate_detailed_analysis(df, test_plan, metrics)

            return {
                'metrics': metrics,
                'charts': charts,
                'analysis': analysis,
                'raw_data': df.to_dict('records'),
                'summary': self._generate_executive_summary(metrics)
            }

        except Exception as e:
            return {"error": f"生成报告失败: {str(e)}"}

    def _create_metric_card_html(self, title, value, description="", color="default"):
        """创建指标卡片HTML"""
        color_class = {
            "default": "metric-card",
            "red": "metric-card-red",
            "green": "metric-card-green",
            "blue": "metric-card-blue",
            "orange": "metric-card-orange"
        }.get(color, "metric-card")

        return f"""
        <div class="{color_class}">
            <h3>{title}</h3>
            <h1>{value}</h1>
            <small>{description}</small>
        </div>
        """

    def display_report_in_streamlit(self, report_data: Dict):
        """在Streamlit中显示增强版报告"""

        if 'error' in report_data:
            st.error(report_data['error'])
            return

        # 加载CSS样式
        self._load_css_styles()

        metrics = report_data.get('metrics', {})
        bm = metrics.get('benchmark', {})
        charts = report_data.get('charts', {})
        analysis = report_data.get('analysis', {})
        summary = report_data.get('summary', '')

        # === 1. 报告头部 ===
        st.markdown("# 📊 智能可视化报告")
        st.markdown(f"**生成时间:** {metrics.get('execution_time', '未知')}")

        # 显示执行摘要
        if summary:
            with st.container():
                st.markdown("### 📋 执行摘要")
                st.markdown(summary)
                st.markdown("---")

        # === 2. 人机对齐度评估 ===
        if bm:
            st.subheader("1. 🤝 人机对齐度评估 (Human-AI Alignment)")

            # 使用HTML卡片显示指标
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.markdown(self._create_metric_card_html(
                    "✅ 召回率 (Recall)",
                    f"{bm['recall']}%",
                    "AI覆盖了多少人工设计的用例",
                    "blue"
                ), unsafe_allow_html=True)

            with col2:
                st.markdown(self._create_metric_card_html(
                    "🎯 准确率 (Precision)",
                    f"{bm.get('precision', 0)}%",
                    "AI生成的用例符合人工预期的比例",
                    "green"
                ), unsafe_allow_html=True)

            with col3:
                st.markdown(self._create_metric_card_html(
                    "📋 人工基准",
                    f"{bm['human_total']}",
                    "人工设计的测试用例总数",
                    "orange"
                ), unsafe_allow_html=True)

            with col4:
                st.markdown(self._create_metric_card_html(
                    "🎯 AI命中",
                    f"{bm['human_covered']}",
                    "AI覆盖的人工用例数量",
                    "red"
                ), unsafe_allow_html=True)

            # 漏测详情
            if bm.get('missed_list'):
                with st.expander(f"📉 漏测详情 ({len(bm['missed_list'])})", expanded=False):
                    for missed in bm['missed_list']:
                        st.markdown(f"""
                        <div class="missed-case">
                            <strong>{missed.get('api_name', '未知API')}</strong> - {missed.get('type', '未知类型')}<br>
                            <small>{missed.get('description', '无描述')}</small>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("---")

            # === 3. AI智能增广评估 ===
            st.subheader("2. 🚀 AI智能增广评估")

            aug_rate = bm.get('augmentation_rate', 0)
            if aug_rate > 80:
                eval_text = "🌟 高质量增广"
                eval_color = "green"
            elif aug_rate < 50:
                eval_text = "⚠️ 存在幻觉"
                eval_color = "red"
            else:
                eval_text = "🔵 质量尚可"
                eval_color = "blue"

            e1, e2, e3 = st.columns(3)

            with e1:
                st.markdown(self._create_metric_card_html(
                    "📈 额外生成总数",
                    f"+{bm['extra_total']}",
                    "AI额外生成的用例数",
                    "blue"
                ), unsafe_allow_html=True)

            with e2:
                st.markdown(self._create_metric_card_html(
                    "💎 有效增广",
                    f"{bm['extra_valid']}",
                    "额外生成中通过的用例数",
                    "green"
                ), unsafe_allow_html=True)

            with e3:
                st.markdown(self._create_metric_card_html(
                    "📝 评价",
                    eval_text,
                    f"{aug_rate}% 有效率",
                    eval_color
                ), unsafe_allow_html=True)

            # 增广用例详情
            if bm['extra_total'] > 0:
                st.progress(bm['augmentation_rate'] / 100)

                with st.expander(f"🔍 查看 {bm['extra_total']} 个额外生成的用例详情", expanded=False):
                    for extra in bm.get('extra_list', []):
                        if extra.get('type') == 'pass':
                            st.markdown(f"""
                            <div class="extra-case-pass">
                                <strong>✅ [{extra.get('status')}] {extra.get('id')}</strong><br>
                                <small>{extra.get('desc')}</small>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="extra-case-fail">
                                <strong>❌ [{extra.get('status')}] {extra.get('id')}</strong><br>
                                <small>{extra.get('desc')}</small>
                            </div>
                            """, unsafe_allow_html=True)

            st.markdown("---")

        # === 4. 业务执行质量 ===
        st.subheader("3. ⚡ 业务执行质量")

        # 核心指标
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总用例数", metrics.get('total_tests', 0))
        with col2:
            st.metric("通过数", metrics.get('pass_count', 0))
        with col3:
            st.metric("失败数", metrics.get('fail_count', 0))
        with col4:
            st.metric("跳过数", metrics.get('skip_count', 0))

        col5, col6 = st.columns(2)
        with col5:
            st.metric("通过率", f"{metrics.get('pass_rate', 0)}%")
        with col6:
            risk_color = {
                '低风险': 'green',
                '中等风险': 'orange',
                '高风险': 'red',
                '极高风险': 'darkred',
                '未知风险': 'gray',
                '高风险 (核心链路阻断)': 'darkred'
            }.get(metrics.get('risk_level', ''), 'gray')
            st.markdown(f"<h3 style='color: {risk_color};'>风险等级: {metrics.get('risk_level', '未知')}</h3>",
                        unsafe_allow_html=True)

        # === 5. 主要图表 ===
        st.markdown("---")
        st.markdown("### 📈 主要分析图表")

        # 第一行：通过率仪表盘和状态分布
        col1, col2 = st.columns(2)
        with col1:
            if 'summary_gauge' in charts:
                st.plotly_chart(charts['summary_gauge'], use_container_width=True)

        with col2:
            if 'status_distribution' in charts:
                st.plotly_chart(charts['status_distribution'], use_container_width=True)

        # 第二行：场景分析和趋势分析
        col1, col2 = st.columns(2)
        with col1:
            if 'scenario_type_analysis' in charts:
                st.plotly_chart(charts['scenario_type_analysis'], use_container_width=True)

        with col2:
            if 'trend_analysis' in charts:
                st.plotly_chart(charts['trend_analysis'], use_container_width=True)

        # 第三行：失败模式
        if 'failure_pattern' in charts:
            st.plotly_chart(charts['failure_pattern'], use_container_width=True)

        # === 6. SWOT分析 ===
        if analysis:
            st.markdown("---")
            st.markdown("### 🔍 SWOT分析")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if analysis.get('strengths'):
                    st.markdown('<div class="swot-box strengths-box">', unsafe_allow_html=True)
                    st.success("#### 优势 (Strengths)")
                    for strength in analysis['strengths']:
                        st.markdown(f"✅ {strength}")
                    st.markdown('</div>', unsafe_allow_html=True)

            with col2:
                if analysis.get('weaknesses'):
                    st.markdown('<div class="swot-box weaknesses-box">', unsafe_allow_html=True)
                    st.error("#### 劣势 (Weaknesses)")
                    for weakness in analysis['weaknesses']:
                        st.markdown(f"❌ {weakness}")
                    st.markdown('</div>', unsafe_allow_html=True)

            with col3:
                if analysis.get('opportunities'):
                    st.markdown('<div class="swot-box opportunities-box">', unsafe_allow_html=True)
                    st.info("#### 机会 (Opportunities)")
                    for opportunity in analysis['opportunities']:
                        st.markdown(f"🎯 {opportunity}")
                    st.markdown('</div>', unsafe_allow_html=True)

            with col4:
                if analysis.get('threats'):
                    st.markdown('<div class="swot-box threats-box">', unsafe_allow_html=True)
                    st.warning("#### 威胁 (Threats)")
                    for threat in analysis['threats']:
                        st.markdown(f"⚠️ {threat}")
                    st.markdown('</div>', unsafe_allow_html=True)

        # === 7. 优化建议 ===
        if analysis.get('recommendations'):
            st.markdown("---")
            st.markdown("### 💡 优化建议")

            for idx, recommendation in enumerate(analysis['recommendations'], 1):
                st.markdown(f"{idx}. {recommendation}")

        # 额外的改进建议
        st.markdown("---")
        st.subheader("📋 综合改进建议")

        insights = []

        if metrics['pass_rate'] < 70:
            insights.append("🔴 **通过率偏低**: 建议检查环境配置和API连通性")

        if bm and bm.get('recall', 0) < 60:
            insights.append("🟡 **覆盖率不足**: 建议优化AI策略，关注未覆盖的功能点")

        if bm and bm.get('augmentation_rate', 0) < 50:
            insights.append("🟠 **增广质量差**: 建议调整AI提示词，减少无效生成")

        if metrics.get('avg_gen_time', 0) > 10:
            insights.append("⚡ **生成效率低**: 考虑优化LLM调用策略或使用缓存")

        if not insights:
            insights.append("✅ **测试质量良好**: 继续保持！")

        for insight in insights:
            st.markdown(f"- {insight}")

        # === 8. 详细数据 ===
        st.markdown("---")
        st.markdown("### 📋 详细数据")

        raw_data = report_data.get('raw_data', [])
        if raw_data:
            df_display = pd.DataFrame(raw_data)

            # 添加颜色高亮
            def highlight_status(val):
                if val == 'PASS':
                    return 'background-color: #90EE90; color: black;'
                elif val == 'FAIL':
                    return 'background-color: #FFB6C1; color: black;'
                elif val == 'SKIP':
                    return 'background-color: #FFE4B5; color: black;'
                elif 'PASS' in val:
                    return 'background-color: #e2d9ff; color: black;'
                return ''

            display_cols = ['id', 'status']
            styled_df = df_display[display_cols].style.applymap(
                highlight_status, subset=['status']
            )
            st.dataframe(styled_df, use_container_width=True, height=300)

            # 获取数据中存储的执行时间 (例如 "2023-10-27 10:00:00")
            exec_time_str = metrics.get('execution_time', 'report')
            # 替换空格和冒号，使其成为合法文件名
            safe_time_str = str(exec_time_str).replace(' ', '_').replace(':', '-')
            fixed_file_name = f"test_report_{safe_time_str}.csv"

            # 转换 CSV
            csv = df_display.to_csv(index=False).encode('utf-8')

            st.download_button(
                label="📥 下载CSV数据",
                data=csv,
                file_name=fixed_file_name,
                mime="text/csv",
                key="btn_download_report_engine",
                use_container_width=True
            )