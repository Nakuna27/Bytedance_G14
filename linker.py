import json
import copy
import re
import itertools
from collections import deque, defaultdict


# --- 辅助函数：深度查找 Body/Params 中所有潜在的 ID 依赖 ---
def extract_dependencies(data):
    """递归查找 Body 或 Params 中所有可能代表 ID 的字段名。"""
    dependencies = set()
    if isinstance(data, dict):
        for k, v in data.items():
            key_lower = k.lower()
            if key_lower.endswith('_id') or 'parent' in key_lower or 'target' in key_lower or 'uuid' in key_lower:
                if not isinstance(v, str) or (
                        "GENERATE_" not in v and "reuse_" not in v and "oc_" not in v and "raw_data" not in v):
                    dependencies.add(k)
            if isinstance(v, (dict, list)):
                dependencies.update(extract_dependencies(v))
    elif isinstance(data, list):
        for item in data:
            dependencies.update(extract_dependencies(item))
    return dependencies


def auto_link_process():
    print("🧠 [Linker] 启动【DAG调度·全接口深度泛用版】智能引擎...")
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            raw_list = json.load(f)
    except:
        return []

    resource_groups = {}
    for api in raw_list:
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        base_path = re.sub(r'/:.*', '', clean_url)
        parts = base_path.split('/')
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
    single_res_name = res_name[:-1] if res_name.endswith('s') else res_name
    VAR_ID = f"auto_{single_res_name}_id"

    producer = None
    consumers = []
    list_api = None

    for api in api_group:
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        if api['method'] == 'GET' and ":" not in clean_url:
            list_api = api
        elif api[
            'method'] == 'POST' and ":" not in clean_url and "search" not in clean_url and "merge" not in clean_url:
            if not producer: producer = api
        elif ":" in clean_url:
            consumers.append(api)

    def process(step, extract_var=None, inject_map=None, invalid_id=None, override_body=None):
        s = copy.deepcopy(step)
        if 'body' not in s: s['body'] = {}
        if 'params' not in s: s['params'] = {}
        if override_body: s['body'].update(override_body)

        if extract_var:
            guessed_id = f"{single_res_name}_id"
            s['extract'] = {extract_var: f"data.{guessed_id}"}

        if inject_map:
            for id_key, id_val in inject_map.items():
                s['url'] = re.sub(r':\w+', f"${id_val}", s['url'])
            for k, v in s['body'].items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and "DEPENDENCY" in v[0]:
                    s['body'][k] = [f"${val}" for val in inject_map.values()]

        if invalid_id:
            s['url'] = re.sub(r':\w+', invalid_id, s['url'])
            keys_to_rm = [k for k in s['params'] if k in step['url']]
            for k in keys_to_rm: del s['params'][k]
        return s

    consumers.sort(key=lambda x: {"GET": 1, "PUT": 2, "PATCH": 2, "POST": 3, "DELETE": 100}.get(x['method'], 50))
    scenarios = []
    del_api = next((c for c in consumers if c['method'] == 'DELETE'), None)

    # 1. Lifecycle
    if producer:
        steps_full = [process(producer, extract_var=VAR_ID)]
        for c in consumers:
            if "batch" not in c['url'] and "merge" not in c['url']:
                steps_full.append(process(c, inject_map={"id": VAR_ID}))

        scenarios.append({
            "scenario_name": f"test_{res_name}_00_lifecycle",
            "description": f"✅ [{res_name}] 业务闭环 (CRUD)",
            "steps": steps_full
        })

        # 2. Idempotency
        scenarios.append({
            "scenario_name": f"test_{res_name}_02_idempotency",
            "description": f"🛡️ [{res_name}] 幂等性测试",
            "steps": [
                process(producer, extract_var=f"{VAR_ID}_idem_1", override_body={'uuid': 'GENERATE_UUID'}),
                process(producer, extract_var=f"{VAR_ID}_idem_2", override_body={'uuid': 'reuse_uuid_from_step_1'})
            ]
        })

    # 3. Universal Mutation
    mutation_targets = []
    if producer: mutation_targets.append({"api": producer, "role": "producer"})
    for c in consumers:
        if c.get('body') and c['method'] != 'DELETE':
            mutation_targets.append({"api": c, "role": "consumer"})

    for target_info in mutation_targets:
        target_api = target_info["api"]
        role = target_info["role"]
        api_id = target_api.get('case_name', f"{target_api['method']}_{target_api['url'][-10:]}")

        for key, value in target_api['body'].items():
            mutations = [
                ("miss", "缺参", lambda k, b: b.pop(k, None)),
                ("overflow", "溢出", lambda k, b: b.update({k: "__OVERFLOW__"}) if isinstance(value, str) else None),
                ("type", "类型错误", lambda k, b: b.update({k: "__WRONG_TYPE__"}) if isinstance(value, str) else None)
            ]

            for mut_code, mut_desc, mut_action in mutations:
                mutated_body = copy.deepcopy(target_api['body'])
                if mut_action(key, mutated_body) is False: continue

                steps = []
                if role == "producer":
                    s_mut = process(target_api)
                    s_mut['body'] = mutated_body
                    s_mut['description'] += " ❌"
                    steps.append(s_mut)
                elif role == "consumer" and producer:
                    steps.append(process(producer, extract_var=VAR_ID))
                    s_mut = process(target_api, inject_map={"id": VAR_ID})
                    s_mut['body'] = mutated_body
                    s_mut['description'] += f" (针对 {key} 字段) ❌"
                    steps.append(s_mut)
                    if del_api: steps.append(process(del_api, inject_map={"id": VAR_ID}))
                else:
                    continue

                if steps:
                    scenarios.append({
                        "scenario_name": f"test_{res_name}_mut_{api_id}_{mut_code}_{key}",
                        "description": f"❌ [{res_name}] {api_id} {mut_desc}: {key}",
                        "steps": steps
                    })

    # 4. Pagination & Exception
    if list_api:
        list_steps = []
        for size in [10, 50]:
            s = process(list_api)
            s['params']['page_size'] = size
            s['description'] = f"列表查询 (Size={size})"
            list_steps.append(s)
        scenarios.append({"scenario_name": f"test_{res_name}_pagination_matrix",
                          "description": f"🔍 [{res_name}] 列表查询参数矩阵测试", "steps": list_steps})

    if del_api:
        s_not_found = process(del_api, invalid_id="invalid_id_999")
        s_not_found['description'] += " ❌"
        scenarios.append(
            {"scenario_name": f"test_{res_name}_res_not_found", "description": f"❌ [{res_name}] 资源不存在测试",
             "steps": [s_not_found]})

    if not producer:
        for c in consumers:
            scenarios.append({"scenario_name": f"test_{res_name}_isolated_robust",
                              "description": f"⚠️ [{res_name}] 孤立接口鲁棒性盲测",
                              "steps": [process(c, invalid_id="mock_id_999")]})

    return scenarios


if __name__ == '__main__': auto_link_process()