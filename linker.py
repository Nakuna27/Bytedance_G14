import json
import copy
import re


def auto_link_process():
    print("🧠 [Linker] 启动【通用型 RESTful】智能引擎...")
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            raw_list = json.load(f)
    except:
        return []

    resource_groups = {}
    for api in raw_list:
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        base_path = re.sub(r'/:.*', '', clean_url)

        # --- 通用资源提取逻辑 ---
        # 假设 URL 倒数第一段或第二段为资源名 (如 /v1/messages -> messages)
        parts = base_path.split('/')
        resource_name = parts[-1] if parts[-1] else parts[-2]

        if resource_name not in resource_groups: resource_groups[resource_name] = []
        resource_groups[resource_name].append(api)

    final_scenarios = []
    for res_name, api_group in resource_groups.items():
        final_scenarios.extend(build_final_suite(res_name, api_group))

    with open('scenarios.json', 'w', encoding='utf-8') as f:
        json.dump(final_scenarios, f, indent=4, ensure_ascii=False)

    print(f"✅ [Linker] 生成完成！针对资源 {list(resource_groups.keys())} 共裂变出 {len(final_scenarios)} 个通用场景。")
    return final_scenarios


def build_final_suite(res_name, api_group):
    # 通用 ID 变量名生成 (如 users -> auto_user_id)
    single_res_name = res_name[:-1] if res_name.endswith('s') else res_name
    VAR_ID = f"auto_{single_res_name}_id"

    producer = None
    consumers = []
    list_api = None

    for api in api_group:
        clean_url = api['url'].replace("https://", "").replace("http://", "")

        # 1. 识别 List 接口 (GET 且 URL 无参数占位符)
        if api['method'] == 'GET' and ":" not in clean_url:
            list_api = api
        # 2. 识别 Producer (POST 创建资源)
        elif api['method'] == 'POST' and ":" not in clean_url and "merge" not in clean_url:
            if not producer: producer = api
        # 3. 识别 Consumers (操作具体资源，URL 含 :)
        elif ":" in clean_url:
            consumers.append(api)

    def process(step, extract_var=None, inject_map=None, invalid_id=None, override_body=None):
        s = copy.deepcopy(step)
        if 'body' not in s: s['body'] = {}
        if 'params' not in s: s['params'] = {}

        if override_body:
            s['body'].update(override_body)

        if extract_var:
            # --- 通用 ID 猜测策略 ---
            guessed_id = f"{single_res_name}_id"
            s['extract'] = {extract_var: f"data.{guessed_id}"}

        if inject_map:
            for id_key, id_val in inject_map.items():
                s['url'] = re.sub(r':\w+', f"${id_val}", s['url'])

            for k, v in s['body'].items():
                if isinstance(v, list) and (k.endswith('_list') or (len(v) > 0 and "LIST_DEPENDENCY" in str(v[0]))):
                    s['body'][k] = [f"${val}" for val in inject_map.values()]

        if invalid_id:
            s['url'] = re.sub(r':\w+', invalid_id, s['url'])
            keys_to_remove = [k for k in s['params'] if k in step['url']]
            for k in keys_to_remove: del s['params'][k]

        return s

    consumers.sort(key=lambda x: {"GET": 1, "PUT": 2, "PATCH": 2, "POST": 3, "DELETE": 100}.get(x['method'], 50))
    scenarios = []

    if producer:
        # === 1. 标准生命周期 ===
        simple_consumers = [c for c in consumers if "merge" not in c['url']]
        steps_full = [process(producer, extract_var=VAR_ID)]
        for c in simple_consumers:
            s = process(c, inject_map={"id": VAR_ID})
            steps_full.append(s)

        scenarios.append({
            "scenario_name": f"test_{res_name}_00_lifecycle",
            "description": f"✅ [{res_name}] 业务闭环 (CRUD)",
            "steps": steps_full
        })

        # === 2. 幂等性测试 ===
        step1 = process(producer, extract_var=f"{VAR_ID}_idem_1")
        step1['body']['uuid'] = "GENERATE_UUID"
        step2 = process(producer, extract_var=f"{VAR_ID}_idem_2")
        step2['body']['uuid'] = "reuse_uuid_from_step_1"

        scenarios.append({
            "scenario_name": f"test_{res_name}_02_idempotency",
            "description": f"🛡️ [{res_name}] 幂等性测试",
            "steps": [step1, step2]
        })

        # === 3. 泛型变异测试 ===
        target = producer
        if target.get('body'):
            for key, value in target['body'].items():
                s_miss = process(target, extract_var=VAR_ID)
                if key in s_miss['body']: del s_miss['body'][key]
                s_miss['description'] += " ❌"
                scenarios.append({
                    "scenario_name": f"test_{res_name}_mut_miss_{key}",
                    "description": f"❌ [{res_name}] 缺参测试: {key}",
                    "steps": [s_miss]
                })

                if isinstance(value, str):
                    s_over = process(target, extract_var=VAR_ID)
                    s_over['body'][key] = "__OVERFLOW__"
                    s_over['description'] += " ❌"
                    scenarios.append({
                        "scenario_name": f"test_{res_name}_mut_overflow_{key}",
                        "description": f"❌ [{res_name}] 边界溢出: {key}",
                        "steps": [s_over]
                    })

                    s_type = process(target, extract_var=VAR_ID)
                    s_type['body'][key] = "__WRONG_TYPE__"
                    s_type['description'] += " ❌"
                    scenarios.append({
                        "scenario_name": f"test_{res_name}_mut_type_{key}",
                        "description": f"❌ [{res_name}] 类型错误: {key}",
                        "steps": [s_type]
                    })

    # === 4. 分页测试 ===
    if list_api:
        s_list_p1 = process(list_api)
        s_list_p1['params']['page_size'] = 5
        s_list_p1['description'] += " (Page 1)"
        scenarios.append({
            "scenario_name": f"test_{res_name}_pagination",
            "description": f"🔍 [{res_name}] 列表分页查询",
            "steps": [s_list_p1]
        })

    # === 5. 孤立测试 ===
    if not producer:
        for c in consumers:
            scenarios.append({
                "scenario_name": f"test_{res_name}_isolated_robust",
                "description": f"⚠️ [{res_name}] 孤立测试",
                "steps": [process(c, invalid_id="mock_id_999")]
            })
    else:
        del_api = next((c for c in consumers if c['method'] == 'DELETE'), None)
        if del_api:
            s_not_found = process(del_api, invalid_id="invalid_id_999")
            s_not_found['description'] += " ❌"
            scenarios.append({
                "scenario_name": f"test_{res_name}_res_not_found",
                "description": f"❌ [{res_name}] 资源不存在",
                "steps": [s_not_found]
            })

    return scenarios


if __name__ == '__main__': auto_link_process()