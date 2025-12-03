import json
from jinja2 import Template
from linker import auto_link_process


def analyze_and_report(scenarios):
    print("\n" + "=" * 60)
    print("📊 [智能自动化平台 - 深度智能版评估报告]")
    print("=" * 60)

    count = len(scenarios)
    scenario_names = [s['scenario_name'] for s in scenarios]
    print(f"检测到已裂变出 {count} 个通用测试场景。")

    score = 0
    if count > 0: score += 20

    if any("lifecycle" in name for name in scenario_names): score += 30

    has_miss = any("mut" in name and "miss" in name for name in scenario_names)
    has_overflow = any("mut" in name and "overflow" in name for name in scenario_names)
    has_type = any("mut" in name and "type" in name for name in scenario_names)

    if has_miss: score += 20
    if has_overflow: score += 15
    if has_type: score += 15

    print("-" * 60)
    print(f"🏆 最终智能评分: {score} / 100")
    print("-" * 60)

    if score == 100:
        print("🎉 完美: 您的测试设计已达到 L5 级自动化标准！")
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
    except Exception as e:
        print(f"❌ 生成代码失败: {e}")


if __name__ == '__main__':
    run_platform()