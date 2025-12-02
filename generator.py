import json
from jinja2 import Template
from linker import auto_link_process


def analyze_and_report(scenarios):
    print("\n" + "=" * 60)
    print("📊 [智能自动化平台 - 动态评估报告]")
    print("=" * 60)

    count = len(scenarios)
    scenario_names = [s['scenario_name'] for s in scenarios]
    print(f"检测到已生成 {count} 个测试场景。")

    score = 0
    if count > 0: score += 20
    if any("lifecycle" in name for name in scenario_names): score += 40
    if any("validation" in name or "isolated" in name for name in scenario_names): score += 40

    print("-" * 60)
    print(f"🏆 最终智能评分: {score} / 100")
    print("-" * 60)

    if score == 100:
        print("✅ 完美: 已覆盖多资源、全链路及异常测试！")
    print("=" * 60 + "\n")


def run_platform():
    generated_data = auto_link_process()
    if not generated_data: return

    analyze_and_report(generated_data)

    try:
        with open('template_scenario.j2', 'r', encoding='utf-8') as f:
            template_content = f.read()
        template = Template(template_content)
        generated_code = template.render(scenarios=generated_data)

        output_file = 'test_final_suite.py'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(generated_code)

        print(f"✅ 测试脚本已生成: {output_file}")
        print("👉 运行: pytest test_final_suite.py --html=report.html --self-contained-html -s")
    except Exception as e:
        print(f"❌ 生成代码失败: {e}")


if __name__ == '__main__':
    run_platform()