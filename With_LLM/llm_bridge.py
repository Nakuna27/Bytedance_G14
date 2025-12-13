# llm_bridge.py
import openai
import json
import config
from utils import repair_json_content, extract_code_block
import re


class LLMBridge:
    # ... (前面的 __init__, analyze_topology, _safe_call_and_parse, _call_llm, _post_process_plan 保持不变) ...
    def __init__(self, api_key, api_base, model_name):
        self.client = openai.OpenAI(api_key=api_key, base_url=api_base)
        self.model = model_name

    def analyze_topology(self, docs_dict):
        # ... (保持原样) ...
        doc_summaries = []
        for name, content in docs_dict.items():
            if len(content) > 80000:
                head = content[:10000]
                tail = content[-10000:]
                snippet = f"{head}\n\n...[Truncated]...\n\n{tail}"
            else:
                snippet = content
            doc_summaries.append(f"Filename: {name}\nContent:\n{snippet}")

        combined_summary = "\n\n".join(doc_summaries)

        prompt_sc = config.PROMPT_ANALYZE_SCENARIOS.format(
            docs_content=combined_summary,
            example_scenario=config.EXAMPLE_SCENARIO
        )
        plan_sc = self._safe_call_and_parse(prompt_sc, "链路分析")
        if "error" in plan_sc: return plan_sc

        prompt_sg = config.PROMPT_ANALYZE_SINGLE.format(
            docs_content=combined_summary,
            example_single=config.EXAMPLE_SINGLE
        )
        plan_sg = self._safe_call_and_parse(prompt_sg, "单点分析")
        if "error" in plan_sg: plan_sg = {"single_api_cases": [], "required_env_vars": []}

        final_plan = {
            "scenarios": plan_sc.get("scenarios", []),
            "single_api_cases": plan_sg.get("single_api_cases", []),
            "required_env_vars": list(set(plan_sc.get("required_env_vars", []) + plan_sg.get("required_env_vars", [])))
        }

        return self._post_process_plan(final_plan)

    def _safe_call_and_parse(self, prompt, task_name, retry_count=1):
        content = self._call_llm(prompt, temperature=0.1)
        try:
            cleaned = repair_json_content(content)
            return json.loads(cleaned)
        except Exception as e:
            if retry_count > 0:
                repair_prompt = f"You generated invalid JSON. Error: {str(e)}\nOriginal: {content}\nFix it."
                return self._safe_call_and_parse(repair_prompt, task_name, retry_count - 1)
            return {"error": f"{task_name} JSON Parse Error: {str(e)}"}

    def _call_llm(self, prompt, temperature=0.1, max_tokens=8000):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a QA Architect. Output valid code/JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content

    def _post_process_plan(self, plan):
        ai_envs = plan.get('required_env_vars', [])
        if "API_TOKEN" not in ai_envs: ai_envs.append("API_TOKEN")

        all_content = str(plan).lower()
        if 'chat_id' in all_content and 'TEST_CHAT_ID' not in ai_envs: ai_envs.append('TEST_CHAT_ID')
        if 'user_id' in all_content and 'TEST_USER_ID' not in ai_envs: ai_envs.append('TEST_USER_ID')

        env_config = []
        for key in list(set(ai_envs)):
            is_req = "NO_BOT" not in key and "IMAGE" not in key and "FILE" not in key
            env_config.append({"key": key, "required": is_req})

        plan['env_vars_config'] = env_config
        return plan

    def generate_scenario_code(self, item, docs_dict, host):
        target_name = item.get('api_name') or item.get('name')
        related_docs = ""
        for name, content in docs_dict.items():
            if target_name and target_name in name:
                related_docs += f"\n=== API: {name} ===\n{content}\n"
        if not related_docs:
            for name, content in docs_dict.items():
                related_docs += f"\n=== API: {name} ===\n{content[:2000]}\n"

        utils_context = """
        【utils.py 工具箱】
        1. get_app_context(key): 智能读取环境变量。
        2. DataFactory.generate(key): 生成 Mock 数据。
        3. APIClient: 封装 requests。
        """
        final_context = utils_context + "\n" + related_docs

        prompt = config.PROMPT_SCENARIO_CODE_GEN.format(
            scenario_json=json.dumps(item, ensure_ascii=False),
            api_docs=final_context,
            host=host
        )

        content = self._call_llm(prompt, temperature=0.2)

        match = re.search(r"```python\s*([\s\S]*?)```", content, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if self._is_valid_python(candidate): return candidate

        try:
            cleaned_json = repair_json_content(content)
            data_obj = json.loads(cleaned_json)

            def find_code(obj):
                keys = ["code", "test_code", "script", "content"]
                if isinstance(obj, dict):
                    for k in keys:
                        if k in obj and isinstance(obj[k], str) and "import" in obj[k]:
                            return obj[k]
                    for v in obj.values():
                        res = find_code(v)
                        if res: return res
                return None

            json_candidate = find_code(data_obj)
            if json_candidate and self._is_valid_python(json_candidate):
                return json_candidate
        except:
            pass

        candidate = extract_code_block(content)
        if self._is_valid_python(candidate): return candidate

        if "import pytest" in content:
            idx = content.find("import pytest")
            raw_slice = content[idx:]
            raw_slice = re.sub(r"```.*$", "", raw_slice, flags=re.MULTILINE).strip()
            if self._is_valid_python(raw_slice): return raw_slice

        return "# ERROR: Failed to extract code."

    def _is_valid_python(self, code_str):
        """代码有效性强校验"""
        if not code_str: return False

        cleaned = code_str.strip().lower()
        if cleaned.startswith("{") and "import" not in cleaned[:50]: return False
        if cleaned.startswith("json"): return False

        if "import pytest" not in code_str: return False
        if "from utils" not in code_str: return False

        return True

    def heal_code(self, original_code, error_log):
        prompt = config.PROMPT_SELF_HEAL.format(code=original_code, error_log=error_log)
        content = self._call_llm(prompt, temperature=0.1)
        return extract_code_block(content)

    def generate_report(self, results, item_names):
        prompt = config.PROMPT_EVALUATION.format(
            results=json.dumps(results, ensure_ascii=False),
            scenario_names=json.dumps(item_names, ensure_ascii=False)
        )
        return self._call_llm(prompt, temperature=0.4)