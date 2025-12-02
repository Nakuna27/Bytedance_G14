import json
import copy
import re


def auto_link_process():
    print("🧠 [Linker] 启动【终极逻辑修正版】智能引擎...")
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            raw_list = json.load(f)
    except:
        return []

    resource_groups = {}
    for api in raw_list:
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        base_path = re.sub(r'/:.*', '', clean_url)
        resource_name = base_path.split('/')[-1]
        if resource_name not in resource_groups: resource_groups[resource_name] = []
        resource_groups[resource_name].append(api)

    final_scenarios = []
    for res_name, api_group in resource_groups.items():
        final_scenarios.extend(build_scenarios(res_name, api_group))

    with open('scenarios.json', 'w', encoding='utf-8') as f:
        json.dump(final_scenarios, f, indent=4, ensure_ascii=False)

    print(f"✅ [Linker] 生成完成！共 {len(final_scenarios)} 个场景。")
    return final_scenarios


def build_scenarios(res_name, api_group):
    VAR_ID = f"auto_{res_name}_id"
    producer = None
    consumers = []

    for api in api_group:
        clean_url = api['url'].replace("https://", "").replace("http://", "")
        # 生产者: POST 且 URL 无参数
        if api['method'] == 'POST' and ":" not in clean_url:
            if not producer: producer = api
        # 消费者: URL 有参数 (必须依赖ID)
        elif ":" in clean_url:
            consumers.append(api)

    def process(step, is_producer=False, invalid_id=None):
        s = copy.deepcopy(step)
        if 'body' not in s: s['body'] = {}
        if 'params' not in s: s['params'] = {}
        if is_producer:
            if 'extract' not in s:
                # 智能推导 ID
                if res_name == 'messages':
                    guessed = 'message_id'
                elif res_name.endswith('es'):
                    guessed = f"{res_name[:-2]}_id"
                elif res_name.endswith('s'):
                    guessed = f"{res_name[:-1]}_id"
                else:
                    guessed = f"{res_name}_id"
                s['extract'] = {VAR_ID: f"data.{guessed}"}
        else:
            id_val = invalid_id if invalid_id else f"${VAR_ID}"
            s['url'] = re.sub(r':\w+', id_val, s['url'])
            keys_to_remove = [k for k in s['params'] if k in step['url']]
            for k in keys_to_remove: del s['params'][k]
        return s

    # 排序：DELETE 必须在最后
    def get_sort_key(x):
        m = x['method'].upper()
        if m == 'DELETE': return 100
        if m in ['PUT', 'PATCH']: return 20
        if m == 'POST': return 30
        return 10

    consumers.sort(key=get_sort_key)

    scenarios = []

    if producer:
        # 1. 全链路
        steps_full = [process(producer, True)] + [process(c) for c in consumers]
        scenarios.append({"scenario_name": f"test_{res_name}_01_lifecycle", "description": f"✅ [{res_name}] 全链路闭环",
                          "steps": steps_full})

        # 2. 冒烟
        del_api = next((c for c in consumers if c['method'] == 'DELETE'), None)
        if del_api:
            scenarios.append({"scenario_name": f"test_{res_name}_02_smoke", "description": f"✅ [{res_name}] 冒烟测试",
                              "steps": [process(producer, True), process(del_api)]})

        # 3. 逆向鉴权
        s_no_auth = process(producer, True);
        s_no_auth['headers'] = {}
        s_no_auth['description'] += " ❌"
        scenarios.append({"scenario_name": f"test_{res_name}_03_no_auth", "description": f"❌ [{res_name}] 鉴权失败",
                          "steps": [s_no_auth]})

        # 4. 逆向资源
        if del_api:
            s_404 = process(del_api, invalid_id="invalid_id_999")
            s_404['description'] += " ❌"
            scenarios.append(
                {"scenario_name": f"test_{res_name}_04_not_found", "description": f"❌ [{res_name}] 资源不存在",
                 "steps": [s_404]})

        # 5. 逆向参数
        s_bad = process(producer, True)
        if s_bad['body']:
            k = list(s_bad['body'].keys())[0]
            del s_bad['body'][k]
            s_bad['description'] += " ❌"
            scenarios.append(
                {"scenario_name": f"test_{res_name}_05_validation", "description": f"❌ [{res_name}] 参数缺失",
                 "steps": [s_bad]})

        # 6. 删后操作 (关键修复)
        if del_api:
            # 🌟 修复：只选 PUT 或 PATCH 作为最后一步，确保操作的是已删除的资源
            other = next((c for c in consumers if c['method'] in ['PUT', 'PATCH']), None)

            if other:
                s_fail = process(other)
                s_fail['description'] += " ❌"  # 只有最后一步预期失败
                scenarios.append({
                    "scenario_name": f"test_{res_name}_06_op_after_delete",
                    "description": f"❌ [{res_name}] 删后操作测试",
                    "steps": [process(producer, True), process(del_api), s_fail]
                })
    else:
        for c in consumers:
            s_iso = process(c, invalid_id="mock_id_999")
            s_iso['description'] += " ❌"
            scenarios.append({"scenario_name": f"test_{res_name}_isolated", "description": f"⚠️ [{res_name}] 孤立测试",
                              "steps": [s_iso]})

    return scenarios


if __name__ == '__main__': auto_link_process()