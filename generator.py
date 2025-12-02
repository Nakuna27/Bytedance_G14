import json
from jinja2 import Template
from linker import auto_link_process


def analyze_and_report(scenarios):
    print("\n" + "=" * 60)
    print("📊 [智能自动化平台 - 通用版评估报告]")
    print("=" * 60)

    count = len(scenarios)
    scenario_names = [s['scenario_name'] for s in scenarios]
    print(f"检测到已裂变出 {count} 个通用测试场景。")

    score = 0
    if count > 0: score += 20

    # 1. 核心业务 (Lifecycle)
    if any("lifecycle" in name for name in scenario_names):
        score += 30
        print("  ✅ 已覆盖: 业务全链路闭环 (Lifecycle)")

    # 2. 变异测试 (Mutation) - 修复匹配逻辑: 只要同时包含 mut 和 miss 即可
    has_miss = any("mut" in name and "miss" in name for name in scenario_names)
    has_overflow = any("mut" in name and "overflow" in name for name in scenario_names)
    has_type = any("mut" in name and "type" in name for name in scenario_names)

    if has_miss:
        score += 20
        print("  ✅ 已覆盖: 缺参变异测试 (Missing Params)")
    if has_overflow:
        score += 15
        print("  ✅ 已覆盖: 边界溢出测试 (Boundary Overflow)")
    if has_type:
        score += 15
        print("  ✅ 已覆盖: 类型错误测试 (Type Mismatch)")

    print("-" * 60)
    print(f"🏆 最终智能评分: {score} / 100")
    print("-" * 60)

    if score == 100:
        print("🎉 完美: 您的测试设计已达到 L5 级自动化标准！")
        print("   (覆盖了: 正向链路 + 逆向变异 + 边界测试 + 智能容错)")
    print("=" * 60 + "\n")


def run_platform():
    # 1. 运行 Linker 生成场景数据
    generated_data = auto_link_process()
    if not generated_data: return

    # 2. 分析覆盖率
    analyze_and_report(generated_data)

    # 3. 渲染代码
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