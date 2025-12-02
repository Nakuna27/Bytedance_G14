import json
import copy
import re
import itertools


def auto_link_process():
    print("🧠 [Linker] 启动【全接口·深度泛用版】智能引擎...")
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            raw_list = json.load(f)
    except:
        return []

    # --- 1. 资源自动分组 (Generic Resource Grouping) ---
    resource_groups = {}
    for api in raw_list:
        # 移除 http/https 前缀
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        # 去掉 URL 参数部分 (/:id)
        base_path = re.sub(r'/:.*', '', clean_url)
        # 自动提取资源名 (取路径最后一段，如 /v1/messages -> messages)
        parts = base_path.split('/')
        # 排除版本号 (v1, v2)
        resource_name = parts[-1] if not re.match(r'v\d+', parts[-1]) else parts[-2]

        if resource_name not in resource_groups: resource_groups[resource_name] = []
        resource_groups[resource_name].append(api)

    final_scenarios = []
    for res_name, api_group in resource_groups.items():
        final_scenarios.extend(build_final_suite(res_name, api_group))

    with open('scenarios.json', 'w', encoding='utf-8') as f:
        json.dump(final_scenarios, f, indent=4, ensure_ascii=False)

    print(f"✅ [Linker] 生成完成！覆盖资源: {list(resource_groups.keys())}，共裂变出 {len(final_scenarios)} 个测试场景。")
    return final_scenarios


def build_final_suite(res_name, api_group):
    # --- 通用 ID 变量推断 ---
    # 规则：复数转单数 (users -> user) + _id
    single_res_name = res_name[:-1] if res_name.endswith('s') else res_name
    VAR_ID = f"auto_{single_res_name}_id"

    producer = None
    consumers = []
    list_api = None

    # --- 角色识别 ---
    for api in api_group:
        clean_url = api['url'].replace("https://", "").replace("http://", "")

        # 列表接口: GET 且无参数
        if api['method'] == 'GET' and ":" not in clean_url:
            list_api = api
        # 生产者: POST 且无参数 (通常是创建)
        elif api['method'] == 'POST' and ":" not in clean_url and "search" not in clean_url:
            if not producer: producer = api
        # 消费者: URL 中包含参数 (如 :id)
        elif ":" in clean_url:
            consumers.append(api)

    # 辅助：步骤处理函数
    def process(step, extract_var=None, inject_map=None, invalid_id=None, override_body=None):
        s = copy.deepcopy(step)
        if 'body' not in s: s['body'] = {}
        if 'params' not in s: s['params'] = {}

        if override_body: s['body'].update(override_body)

        if extract_var:
            # 智能猜测响应体中的 ID 字段
            guessed_id = f"{single_res_name}_id"  # 默认猜测
            # 这里可以扩展：根据 response schema 动态查找 id 字段
            s['extract'] = {extract_var: f"data.{guessed_id}"}

        if inject_map:
            for id_key, id_val in inject_map.items():
                s['url'] = re.sub(r':\w+', f"${id_val}", s['url'])
            # 列表注入支持
            for k, v in s['body'].items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and "DEPENDENCY" in v[0]:
                    s['body'][k] = [f"${val}" for val in inject_map.values()]

        if invalid_id:
            s['url'] = re.sub(r':\w+', invalid_id, s['url'])
            keys_to_rm = [k for k in s['params'] if k in step['url']]
            for k in keys_to_rm: del s['params'][k]

        return s

    # 排序: GET -> PUT -> POST -> DELETE
    consumers.sort(key=lambda x: {"GET": 1, "PUT": 2, "PATCH": 2, "POST": 3, "DELETE": 100}.get(x['method'], 50))
    scenarios = []

    # 查找删除接口作为 Teardown
    del_api = next((c for c in consumers if c['method'] == 'DELETE'), None)

    # ==========================================
    # 1. 业务全链路 (Happy Path Lifecycle)
    # ==========================================
    if producer:
        steps_full = [process(producer, extract_var=VAR_ID)]
        for c in consumers:
            # 排除特殊的合并/批处理接口，只测单体资源
            if "batch" not in c['url'] and "merge" not in c['url']:
                steps_full.append(process(c, inject_map={"id": VAR_ID}))

        scenarios.append({
            "scenario_name": f"test_{res_name}_00_lifecycle",
            "description": f"✅ [{res_name}] 业务闭环 (CRUD)",
            "steps": steps_full
        })

        # 幂等性测试
        scenarios.append({
            "scenario_name": f"test_{res_name}_02_idempotency",
            "description": f"🛡️ [{res_name}] 幂等性测试",
            "steps": [
                process(producer, extract_var=f"{VAR_ID}_1", override_body={'uuid': 'GENERATE_UUID'}),
                process(producer, extract_var=f"{VAR_ID}_2", override_body={'uuid': 'reuse_uuid_from_step_1'})
            ]
        })

    # ==========================================
    # 2. 列表查询矩阵测试 (List Matrix)
    # ==========================================
    if list_api:
        # 智能生成参数组合 (简单 Pairwise 模拟)
        base_params = list_api.get('params', {})
        # 如果有分页参数，生成边界值组合
        if 'page_size' in base_params:
            for size in [10, 50]:
                s = process(list_api)
                s['params']['page_size'] = size
                scenarios.append({
                    "scenario_name": f"test_{res_name}_list_size_{size}",
                    "description": f"🔍 [{res_name}] 列表查询 (Size={size})",
                    "steps": [s]
                })
        else:
            # 默认列表测试
            scenarios.append({
                "scenario_name": f"test_{res_name}_list_default",
                "description": f"🔍 [{res_name}] 列表查询 (默认)",
                "steps": [process(list_api)]
            })

    # ==========================================
    # 3. 全接口深度变异测试 (Universal Deep Mutation)
    # ==========================================
    # 收集所有有 Body 的接口作为攻击目标
    mutation_targets = []
    if producer: mutation_targets.append({"api": producer, "role": "producer"})
    for c in consumers:
        if c.get('body') and c['method'] != 'DELETE':  # DELETE通常无Body
            mutation_targets.append({"api": c, "role": "consumer"})

    for target_info in mutation_targets:
        target_api = target_info["api"]
        role = target_info["role"]
        # 生成唯一标识符
        api_id = target_api.get('case_name', f"{target_api['method']}_{target_api['url'][-10:]}")

        # 遍历 Body 的每一个字段进行攻击
        for key, value in target_api['body'].items():
            mutations = [
                ("miss", "缺参", lambda k, b: b.pop(k, None)),
                ("overflow", "溢出", lambda k, b: b.update({k: "__OVERFLOW__"}) if isinstance(value, str) else None),
                ("type", "类型错误", lambda k, b: b.update({k: "__WRONG_TYPE__"}) if isinstance(value, str) else None)
            ]

            for mut_code, mut_desc, mut_action in mutations:
                mutated_body = copy.deepcopy(target_api['body'])
                # 如果变异动作不适用（返回 None/False），跳过
                if mut_action(key, mutated_body) is False: continue

                steps = []
                # 场景 A: 攻击生产者 (直接发包)
                if role == "producer":
                    s_mut = process(target_api)
                    s_mut['body'] = mutated_body
                    s_mut['description'] += " ❌"
                    steps.append(s_mut)

                # 场景 B: 攻击消费者 (创建 -> 攻击 -> 清理)
                # 只有当存在生产者时才能构建此场景
                elif role == "consumer" and producer:
                    # Step 1: Setup
                    steps.append(process(producer, extract_var=VAR_ID))
                    # Step 2: Attack
                    s_mut = process(target_api, inject_map={"id": VAR_ID})
                    s_mut['body'] = mutated_body
                    s_mut['description'] += f" (针对 {key} 字段) ❌"
                    steps.append(s_mut)
                    # Step 3: Teardown
                    if del_api: steps.append(process(del_api, inject_map={"id": VAR_ID}))
                else:
                    continue

                if steps:
                    scenarios.append({
                        "scenario_name": f"test_{res_name}_mut_{api_id}_{mut_code}_{key}",
                        "description": f"❌ [{res_name}] {api_id} {mut_desc}: {key}",
                        "steps": steps
                    })

    # ==========================================
    # 4. 异常与孤立测试
    # ==========================================
    if del_api:
        # 资源不存在测试
        s_not_found = process(del_api, invalid_id="invalid_id_999")
        s_not_found['description'] += " ❌"
        scenarios.append({
            "scenario_name": f"test_{res_name}_res_not_found",
            "description": f"❌ [{res_name}] 资源不存在测试",
            "steps": [s_not_found]
        })

    # 孤立接口盲测 (没有生产者的消费者)
    if not producer:
        for c in consumers:
            scenarios.append({
                "scenario_name": f"test_{res_name}_isolated_robust",
                "description": f"⚠️ [{res_name}] 孤立接口鲁棒性盲测",
                "steps": [process(c, invalid_id="mock_id_999")]
            })

    return scenarios


if __name__ == '__main__': auto_link_process()