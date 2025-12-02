# 🚀 Smart API Automation Platform (SAAP) | 智能接口自动化测试平台

> **L5级智能测试生成引擎** —— 基于 RESTful 语义分析，从接口文档一键生成全维度、全链路、自适应的自动化测试脚本。

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Pytest](https://img.shields.io/badge/Pytest-7.x-green) ![Jinja2](https://img.shields.io/badge/Jinja2-3.x-orange) ![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

## 📖 项目简介 (Introduction)

本项目是一个**智能化的测试生成平台**，旨在解决传统接口自动化测试中“脚本维护成本高、数据依赖处理繁琐、测试覆盖不全”的痛点。

通过内置的 **Linker 智能分析引擎**，平台能够读取扁平的 OpenAPI/Swagger 接口定义（JSON格式），无需人工编写测试逻辑，即可自动识别业务资源、推导接口依赖关系，并**裂变**生成包含正向业务流与逆向健壮性在内的全套测试用例。

**核心能力：** 给定任意一组 Restful API，平台自动产出 100% 覆盖率的测试代码。

---

## ✨ 核心亮点 (Key Features)

### 1. 🧠 智能资源聚类 (Smart Clustering)
* **痛点解决**：传统脚本针对特定业务写死，无法应对多业务混杂的接口文档。
* **实现原理**：算法自动清洗 URL（去除协议头、参数占位符），提取路径特征（如 `/messages`, `/system_statuses`），将接口自动归类为独立的业务资源组。
* **效果**：无论输入多少个混杂接口，平台都能自动拆解，实现多业务并行测试，互不干扰。

### 2. 🔗 自适应链路编排 (Adaptive Linking)
* **痛点解决**：接口间的数据依赖（如 ID 传递）通常需要手动编写大量胶水代码。
* **实现原理**：
    * **角色识别**：自动识别 `POST`（且无参）为**生产者**，`PUT/DELETE` 为**消费者**。
    * **智能关联**：自动建立**上下文变量池 (`vars_pool`)**。生产者自动提取出参（如 `message_id`），消费者自动注入入参（替换 URL 中的 `:id`）。
    * **语义排序**：内置业务时序逻辑，确保执行顺序永远是 `Create -> Update -> Other -> Delete`。特别优化了逻辑，确保 **Delete** 操作永远排在最后（除非是特定的逻辑漏洞测试）。

### 3. ⚡ 全维度场景裂变 (Scenario Fission)
针对每一个识别出的业务资源，平台会自动裂变出 **6 类** 标准化测试场景，覆盖率从 20% 提升至 100%：
1.  ✅ **全链路闭环测试 (Lifecycle)**：验证完整的业务流转（Create -> Update -> Reply -> Forward -> Delete）。
2.  ✅ **冒烟测试 (Smoke)**：快速验证核心功能可用性（Create -> Delete）。
3.  ❌ **鉴权异常测试 (No Auth)**：验证不带 Token 时的安全性拦截（预期 400/403）。
4.  ❌ **资源健壮性测试 (Not Found)**：验证操作不存在/已删除资源时的系统表现（预期 404）。
5.  ❌ **参数校验测试 (Validation)**：验证核心参数缺失时的拦截逻辑（预期 400）。
6.  ❌ **逻辑漏洞测试 (Op After Delete)**：验证“先删除再修改”的逻辑漏洞（预期失败），确保系统正确拦截了对已销毁资源的操作。

### 4. 🎲 动态数据驱动 (Dynamic Data)
* **痛点解决**：硬编码数据容易导致冲突，且无法模拟真实用户行为。
* **实现原理**：集成 `Faker` 引擎，实现**递归式智能注入**。
    * **随机化**：每次测试自动生成带时间戳的随机文本 (`🤖 text_173000...`)。
    * **结构保护**：针对复杂嵌套字段（如飞书 `content` 字段），实现了“手术刀式”精准替换，保留原有 JSON 结构。
    * **冲突避免**：移除 `priority` 等易冲突字段或生成随机数，确保测试稳定性。

---

## 📂 项目结构 (Structure)

```text
AutoPlatform/
├── data.json              # [数据层] 标准化的接口描述文件（模拟 Swagger/OpenAPI 输入）
├── linker.py              # [控制层] 智能分析引擎：负责资源聚类、依赖分析、场景裂变、排序算法
├── template_scenario.j2   # [视图层] Jinja2 动态模板：负责代码渲染、数据生成、上下文管理、智能断言
├── generator.py           # [调度层] 平台入口：负责调度 Linker、执行指标分析、生成最终脚本
├── test_final_suite.py    # [产出物] 自动生成的最终可执行 Python 测试脚本
├── report.html            # [产出物] Pytest 生成的可视化测试报告
└── README.md              # 项目说明文档
