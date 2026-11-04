# 调研：用 cnb.cool（腾讯云 AI Native Git）低成本运行 AI Agent 挖掘 WorldQuant Alpha

> 调研日期：2026-10-31
> 触发源：WQB 社区帖子「如何（不花钱 / 少花钱）使用 AI Agent 挖掘 Alpha」— https://support.worldquantbrain.com/hc/en-us/community/posts/44555293348631

---

## 0. 核心结论速览

**cnb.cool 是腾讯云推出的 AI Native Git 平台**，提供 **免费 CPU 算力 + 免费 AI Credits + NPC（AI Agent）功能**。将 worldquant-miner 这类开源 Alpha 挖掘项目放到 cnb.cool 上，通过 **定时流水线 + 自定义 NPC** 即可在云端自动完成「因子表达式生成 → WQB 仿真回测 → 结果筛选 → 优质因子提交」的完整闭环，**每月可省约 300-800 元 AI API + 服务器费用**。

---

## 1. cnb.cool 平台全景

### 1.1 定位
腾讯云推出的 **"一切皆为代码"** 云原生构建平台，核心特性：

| 能力 | 说明 |
|------|------|
| **AI Native Git** | 类 GitHub 仓库托管（基于 Gitea），但原生集成 AI 能力 |
| **云原生构建** | 通过 `.cnb.yml` 声明式配置 CI/CD 流水线，基于 Docker 生态 |
| **NPC（AI Agent）** | 自定义 AI 角色，在 Issue/PR 中 `@NPC` 即可触发自动化任务 |
| **云原生开发空间** | 分支即开发环境，Web IDE + 一键 AI Coding |
| **Docker 插件生态** | 任意 Docker 镜像可作为构建插件 |

### 1.2 免费额度（社区版，无需学生认证）

| 资源 | 免费额度 | 超额单价 |
|------|---------|---------|
| 云原生构建 - CPU | **160 核时/月** | 0.125 元/核时 |
| 云原生开发 - CPU | **1600 核时/月** | 0.125 元/核时 |
| AI Credits（Token） | **500 credits/月** | 0.05 元/credit |
| 仓库存储 | 100 GiB | 1 元/GiB/月 |
| 对象存储 | 100 GiB | 1 元/GiB/月 |

**计算示例**：用 2 核 CPU 跑 Alpha 挖掘流水线，160 核时 = **80 小时**的免费运行时间，足够每天跑 2.5 小时持续 30 天。

### 1.3 学生/教育用户专属加码

启悟学习社区（https://qiwoo.edu.cn）的师生用户可额外获得：
- 云原生开发 16,000 核时/月（日常 10 倍）
- AI Credits 6,666 Credits/月（日常 13 倍，约 1 亿 token）

---

## 2. NPC（Non-Player Character）—— 你的 Alpha 挖掘 AI Agent

### 2.1 什么是 NPC

NPC 是 cnb.cool 的核心 AI Agent 机制：
- **触发方式**：在 Issue 或 PR 评论里 `@NPC名字` + 描述需求
- **执行方式**：自动启动一条云原生构建流水线，由 AI Agent 在容器中完成任务
- **工作模式**：自动回复 Issue → 生成代码 → 推送分支 → 提 PR → 跑 CI → 闭环解决
- **隔离身份**：所有 NPC 操作统一显示为 `NPC` 身份，与真人提交区分

### 2.2 系统内置 NPC

| NPC | 用途 |
|-----|------|
| `@CodeBuddy` | 默认 AI 编码助手，开箱即用 |
| `@π` | 通用问答辅助 |
| `@OpenClaw 🦞` | OpenClaw 开源个人 AI 智能体（已出圈） |

### 2.3 自定义 NPC 配置

在仓库根目录创建 `.cnb/settings.yml`：

```yaml
npc:
  roles:
    - name: AlphaMiner
      slogan: "我替你挖因子，你替我自由！"
      prompt: |
        你是 WorldQuant BRAIN Alpha 挖掘专家。
        你的任务是：
        1. 基于给定的因子模板生成新表达式
        2. 调用 WQB API 进行仿真回测
        3. 筛选 Sharpe ≥ 1.5 的因子
        4. 输出结果报告
        
        生成表达式时请遵循以下模板：
        - F1c 模板: vector_neut(rank(ts_arg_min(...)), rank(ts_delta(...)))
        - 三条腿混合结构优先
```

然后在 `.cnb.yml` 中配置 NPC 触发流水线：

```yaml
# NPC 流水线模板
.alpha-miner-npc: &alpha-miner-npc
  - stages:
      - name: 因子挖掘流水线
        image: cnbcool/python:3.10  # 或自定义 Docker 镜像
        env:
          WQB_EMAIL: ${{ secrets.WQB_EMAIL }}
          WQB_PASSWORD: ${{ secrets.WQB_PASSWORD }}
        script: |
          git clone $CNB_REPO_URL -b $CNB_BRANCH
          pip install -r requirements.txt
          python run_alpha_miner.py --prompt "$CNB_NPC_PROMPT" \
              --output reports/alpha-$(date +%s).md
          # 结果自动回贴到 Issue

# 触发规则
AlphaMiner:
  issue.comment@npc: *alpha-miner-npc
  pull_request.comment@npc: *alpha-miner-npc

# 默认兜底
$:
  issue.comment@npc: *alpha-miner-npc
```

### 2.4 NPC 触发事件类型

| 事件 | 说明 |
|------|------|
| `issue.comment@npc` | Issue 评论中 @NPC |
| `pull_request.comment@npc` | PR 评论中 @NPC |
| API 调用 | 通过 OPENAPI 远程触发 |
| **定时任务** | **最适合 Alpha 挖掘！每天定时自动跑** |

---

## 3. 定时流水线 —— 全自动挖 Alpha 的关键

Alpha 挖掘不需要人盯着，可以用 cnb.cool 的 **定时触发** 每天自动跑：

### 3.1 定时配置

在 `.cnb.yml` 中添加：

```yaml
# 每天凌晨 2 点自动运行 Alpha 挖掘
schedule:
  - cron: "0 2 * * *"
    stages:
      - name: 每日 Alpha 自动挖掘
        image: cnbcool/python:3.10
        env:
          WQB_EMAIL: ${{ secrets.WQB_EMAIL }}
          WQB_PASSWORD: ${{ secrets.WQB_PASSWORD }}
        script: |
          git clone $CNB_REPO_URL -b main
          pip install -r requirements.txt qbrain
          # 批量跑 50 个候选因子
          python batch_mine.py \
              --templates templates/f1c.yaml \
              --count 50 \
              --universe TOP3000 \
              --delay 1 \
              --min-sharpe 1.58 \
              --submit-queue auto \
              --output reports/daily-$(date +%Y%m%d).md
```

### 3.2 定时触发 vs NPC 触发的对比

| 维度 | 定时流水线 | NPC 手动触发 |
|------|-----------|-------------|
| 自动化程度 | 全自动，无需干预 | 手动 @ 触发 |
| 适用场景 | 大规模批量挖掘 | 精准定向挖掘 / 调优 |
| 资源消耗 | 可控（每天固定配额） | 按需 |
| 反馈方式 | 写入仓库文件 / Issue 回帖 | 直接 Issue 回帖 |
| 最佳实践 | **定时跑 90% 算力** | 手动 @ 做 10% 调优 |

---

## 4. Alpha 挖掘引擎选型

### 4.1 开源项目对比

| 项目 | LLM 方案 | 回测 | 提交 | 亮点 |
|------|---------|------|------|------|
| **[worldquant-miner](https://github.com/zhutoutoutousan/worldquant-miner)** | Ollama 本地模型 / Dify API | ✅ 自动 | ✅ 自动 | 三引擎架构（Naive-Ollama / Gen Two / Mini-Quant），含 Web Dashboard |
| **wq-alpha-research**（你当前项目） | MCP Server（cnhkmcp） | ✅ FULL 闸门 | - | F1c 模板库 + 三条腿混合结构实践 |
| **QuantGPT MCP** | Claude/Cursor | ✅ | ✅ | MCP Server，可嵌入任意 AI 编辑器 |
| **OpenClaw + worldquant skill** | OpenClaw 本地 Agent | ✅ | ✅ | 轻量化，Docker 一键部署 |

### 4.2 cnb.cool 上的最佳组合方案

```
┌──────────────────────────────────────────────────────────────┐
│  cnb.cool 仓库: alpha-miner                                  │
│                                                              │
│  ┌─────────────────┐    ┌──────────────────┐                │
│  │ 定时流水线       │    │ 自定义 NPC        │                │
│  │ cron: "0 2 * *" │    │ @AlphaMiner       │                │
│  └────────┬────────┘    └────────┬─────────┘                │
│           │                       │                          │
│           ▼                       ▼                          │
│  ┌─────────────────────────────────────┐                    │
│  │  Docker 容器 (cnbcool/python:3.10)  │                    │
│  │                                     │                    │
│  │  1. 加载因子模板库 (.yaml)            │                    │
│  │  2. [可选] 调用外部 LLM 生成表达式    │                    │
│  │  3. 调用 WQB qbrain SDK 仿真         │                    │
│  │  4. 筛选 Sharpe ≥ 1.58 的因子        │                    │
│  │  5. 自动提交至 WQB                    │                    │
│  │  6. 写入报告 + 回帖 Issue             │                    │
│  └─────────────────────────────────────┘                    │
│                                                              │
│  免费资源消耗:                                                │
│  - CPU: 2核 × 每天2h = 4核时/天 ≈ 120核时/月 ✅ < 160核时    │
│  - AI Credits: 若用本地 LLM 则 0 ✅                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 成本分析

### 5.1 传统方案 vs cnb.cool 方案

| 成本项 | 传统方案（AWS/阿里云 + API） | cnb.cool 方案 |
|--------|---------------------------|---------------|
| 服务器 2核4G × 24/7 | ¥150-300/月 | **¥0**（160核时免费 = 80小时） |
| LLM API Token | ¥100-500/月 | **¥0**（500 Credits 免费）或用 Ollama 本地 |
| WQB 仿真额度 | ¥0（平台免费） | ¥0 |
| 定时任务 / CI | ¥50-100/月 | **¥0** |
| **合计** | **¥300-900/月** | **¥0-30/月** |

### 5.2 省钱技巧

| 技巧 | 效果 |
|------|------|
| 用 **Ollama 本地模型** 替代 API（cnb.cool 构建节点可拉 Docker 镜像） | AI Credits 消耗从每天数万个 → 0 |
| 定时跑小批量（如每天 20 个因子）而非一次性跑几百个 | CPU 刚好控制在免费额度内 |
| 启悟教育社区认证（在校师生） | 免费额度 ×10，完全够用 |
| 先跑 INTEGRATION 闸门筛选，再跑 FULL | 减少无效仿真消耗 |
| 用 Python 原生表达式生成而非 LLM（模板化 F1c 变体） | 零 AI 成本 |

---

## 6. 实施步骤

### Step 1：注册 cnb.cool
- 访问 https://cnb.cool/ ，GitHub 账号一键登录
- 创建组织（免费）

### Step 2：创建 Alpha 挖掘仓库
```bash
# 可选：本地准备好代码后 push
git clone https://cnb.cool/your-org/alpha-miner.git
# 放入 run_alpha_miner.py、templates/、requirements.txt 等
git push
```

### Step 3：配置构建 Secrets
仓库 → 设置 → Secrets → 添加：
```
WQB_EMAIL=your@email.com
WQB_PASSWORD=your_wqb_password
```

### Step 4：编写 `.cnb.yml`
参考第 2、3 节的示例，配置：
- 定时触发流水线（每天自动跑）
- 自定义 NPC（手动定向触发）

### Step 5：编写因子挖掘脚本
核心逻辑：
```python
# 伪代码
import qbrain  # WorldQuant Brain SDK

# 1. 加载模板库
templates = load_templates("templates/f1c.yaml")

# 2. 生成候选表达式
for template in templates:
    for fields in field_combinations:
        expr = instantiate(template, fields)
        
        # 3. 仿真回测
        result = brain.simulate(
            expression=expr,
            universe="TOP3000",
            delay=1,
            neutralization="INDUSTRY",
            decay=9
        )
        
        # 4. 筛选
        if result["sharpe"] >= 1.58 and result["fitness"] >= 1.0:
            # 5. 提交
            brain.submit_alpha(result["alpha_id"])
            log_good(expr, result)
```

### Step 6：首次手动触发测试
- 仓库页面 → 云原生构建 → 手动触发
- 观察流水线日志，确认 WQB API 连接正常

### Step 7：设置定时任务
`.cnb.yml` 配好 `schedule` cron 后，系统会自动按计划运行

---

## 7. 风险与注意事项

| 风险 | 对策 |
|------|------|
| WQB 仿真额度消耗过快 | 脚本中设置 `--max-simulations 30` 上限，每天限额 |
| cnb.cool 免费额度用尽 | 绑定预算（最低 ¥50），或减少定时频率 |
| WQB 密码泄露 | cnb.cool Secrets 加密存储，日志中自动脱敏 |
| Docker 镜像拉取慢 | 用 `cnbcool/python:3.10` 官方基础镜像，自定义依赖写 requirements.txt |
| Fork 仓库默认不触发流水线 | 仓库设置 → 云原生构建 → 勾选「允许自动触发」 |
| NPC AI Credits 消耗 | 定时流水线不需要 NPC，用原生代码逻辑即可，零 AI 成本 |

---

## 8. 与你当前项目的结合

你在 wq-alpha-research 项目中已验证过的成果：

| 已有资产 | cnb.cool 上的用法 |
|---------|-----------------|
| F1c 模板 | 直接作为 `templates/f1c.yaml` 的模板源 |
| 三条腿混合结构经验 | 在脚本中作为「优质因子优先」的筛选策略 |
| TRI-social-ROE-CFop-d9 等已通过闸门的因子 | 作为 LLM 的 few-shot 示例，让 AI 生成类似结构 |
| FULL 仿真闸门标准（Sharpe ≥ 1.58, Fitness ≥ 1.0） | 直接写入脚本的筛选阈值 |

---

## 参考链接

| 资源 | 链接 |
|------|------|
| cnb.cool 官网 | https://cnb.cool/ |
| cnb.cool 文档 | https://docs.cnb.cool/zh/ |
| NPC 官方指南 | https://docs.cnb.cool/zh/build/npc.html |
| 触发规则（含定时 + NPC） | https://docs.cnb.cool/zh/build/trigger-rule.html |
| 社区版计费说明 | https://cloud.tencent.cn/document/product/1785/116265 |
| NPC 功能介绍（腾讯云） | https://cloud.tencent.cn/developer/article/2636974 |
| worldquant-miner 项目 | https://github.com/zhutoutoutousan/worldquant-miner |
| worldquant-miner DeepWiki | https://deepwiki.com/zhutoutoutousan/worldquant-miner |
| OpenClaw（龙虾 Agent） | https://github.com/openclaw/openclaw |
| 启悟教育社区（免费额度加码） | https://qiwoo.edu.cn |
| WorldQuant Brain SDK (qbrain) | `pip install qbrain` |

---

## 备注：WQB 社区帖子原文

目标帖子「如何（不花钱 / 少花钱）使用 AI Agent 挖掘 Alpha」发布于：
https://support.worldquantbrain.com/hc/en-us/community/posts/44555293348631

该帖子需要 WQB 登录权限才能查看完整内容（WebFetch 和浏览器访问均被登录墙拦截）。本报告的核心方案基于：
1. 帖子标题明确指向 "不花钱/少花钱 + AI Agent"
2. cnb.cool 提供免费 CPU + AI Credits + NPC 云 Agent
3. worldquant-miner 等开源项目提供 Alpha 挖掘引擎
4. 三者组合形成闭环

如果有 WQB 登录权限的朋友能帮忙贴出帖子原文，欢迎补充验证。
