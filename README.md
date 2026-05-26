# WebGAL Forge

项目的重点是用 **function call + JSON Schema + 后端确定性校验** 的方式，把 LLM 生成过程拆成可验证、可重跑、可修复的流水线。

前端运行地址：

```text
http://127.0.0.1:8010
```

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置环境变量

复制配置模板：

```powershell
copy .env.example .env
```

编辑 `.env`：

```powershell
notepad .env
```

示例：

```env
DEEPSEEK_API_KEY=sk-你的DeepSeekKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
MODEL=deepseek-chat

ARK_API_KEY=ark-你的火山方舟Key

LLM_API_MODE=chat
WEBGAL_JOBS_DIR=./jobs
WEBGAL_PORT=8010
WEBGAL_MAX_SCHEMA_RETRIES=2
WEBGAL_MAX_REPAIR_CYCLES=3
```

说明：

- `DEEPSEEK_API_KEY`：用于剧情结构、素材清单、场景蓝图和修复方案生成
- `ARK_API_KEY`：用于图片生成
- 真实 key 只应写入 `.env`，不要提交到 `.env.example`

### 3. 启动服务

```powershell
.\start_backend.ps1
```

打开：

```text
http://127.0.0.1:8010
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
```

正常返回：

```json
{"status":"ok"}
```

## 如何使用

### 通过网页使用

1. 打开 `http://127.0.0.1:8010`
2. 在输入框写入故事或生成要求
3. 选择是否允许先缺图
4. 选择是否生成图片
5. 点击开始生成
6. 在右侧查看状态和 artifacts

### 通过 API 使用

创建任务：

```powershell
$body = @{
  source_material = "给我一个茅屋为秋风所破歌的游戏"
  options = @{
    allow_missing_assets = $true
    generate_assets = $false
  }
} | ConvertTo-Json -Depth 10

$job = Invoke-RestMethod -Method Post http://127.0.0.1:8010/jobs `
  -ContentType "application/json" `
  -Body $body

$job.id
```

运行完整 pipeline：

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8010/jobs/$($job.id)/run" `
  -ContentType "application/json" `
  -Body '{"background":true}'
```

只运行某个阶段：

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8010/jobs/{job_id}/phases/scenes"
```

可用阶段：

```text
narrative
assets
scenes
validation
repair
```

### 通过 CLI 使用

```powershell
python -m webgal_backend.cli run --source story.txt
```

只跑某个阶段：

```powershell
python -m webgal_backend.cli phase {job_id} scenes
```

查看任务状态：

```powershell
python -m webgal_backend.cli status {job_id}
```

## 生成流程

项目完整流程图见：

[PROJECT_FLOWCHART.md](./PROJECT_FLOWCHART.md)

简化流程：

```text
Frontend
  -> POST /jobs
  -> POST /jobs/{job_id}/run
  -> Narrative Plan
  -> Asset Manifest
  -> Scene Batch
  -> Validation
  -> Repair if needed
  -> DONE / FAILED
```

## Pipeline 阶段

### Phase 1: Narrative

调用 function：

```text
emit_narrative_plan
```

产物：

```text
state/narrative_plan.json
state/characters.json
state/variables.json
state/scene_graph.json
state/branch_map.json
state/ending_matrix.json
```

这一阶段负责生成：

- 游戏标题和主题
- 角色设计
- 变量系统
- 场景图
- 分支选择
- 结局矩阵

后端会对 narrative plan 做 schema 校验和语义校验，并自动补齐一些可推断字段，例如 scene file。

### Phase 2: Assets

调用 function：

```text
emit_asset_manifest
```

产物：

```text
assets_manifest.json
```

这一阶段负责生成：

- 背景图清单
- 角色立绘清单
- 可选 CG 清单
- 图片生成 prompt

如果设置：

```json
generate_assets: true
```

后端会调用原 WebGAL asset scripts 生成图片。

### Phase 3: Scenes

调用 function：

```text
emit_scene_batch
```

注意：LLM 不直接返回完整 `.txt` 文件，而是返回短小的 scene blueprint。

示例：

```json
{
  "scene_id": "start",
  "file": "start.txt",
  "background_asset": "bg_start.webp",
  "speaker_character_id": "poet",
  "beats": [
    { "kind": "narration", "text": "秋风卷过茅屋。" },
    { "kind": "dialogue", "text": "我听见屋顶的草被风掀起。" }
  ]
}
```

后端会把 blueprint 渲染成 WebGAL `.txt`。

### Scene Fallback

DeepSeek 有时会因为 function arguments 太长而返回截断 JSON。

为了避免任务直接失败，scene 阶段有 fallback：

```text
narrative_plan + assets_manifest -> fallback scene_batch -> WebGAL .txt
```

fallback 记录会写入：

```text
state/scene_generation_fallback.json
```

### Phase 4: Validation

这一阶段不依赖 LLM。

后端会检查：

- scene 文件是否存在
- WebGAL 语法
- `callScene` 后是否有 `;`
- `end;` 是否只出现在允许的位置
- `jumpLabel` 是否有对应 label
- 资源引用是否存在
- 变量是否定义
- speaker 是否匹配角色
- 文件命名
- 行数限制

产物：

```text
state/validation_report.json
```

### Phase 5: Repair

如果 validation 出现 errors，会调用：

```text
emit_repair_plan
```

后端根据 repair plan 修改：

```text
public/game/scene/*.txt
```

修复记录：

```text
state/repair_log.json
```

最大修复轮数由 `.env` 控制：

```env
WEBGAL_MAX_REPAIR_CYCLES=3
```

## 项目结构

```text
function call and json schema version/
  frontend/
    index.html
    style.css
    app.js

  webgal_backend/
    app.py
    cli.py
    config.py
    contract_context.py
    llm.py
    pipeline.py
    prompts.py
    storage.py
    validators.py

  webgal-game-function-call/
    SKILL.md
    references/
      function-calls.md
      openai-tools.json
      openai-tools.built.json
      schemas/
    scripts/

  jobs/
    {job_id}/
```

## Job 输出结构

每个任务都会生成：

```text
jobs/{job_id}/
  job.json
  assets_manifest.json
  state/
    narrative_plan.json
    characters.json
    variables.json
    scene_graph.json
    branch_map.json
    ending_matrix.json
    scene_batch.json
    scene_generation_fallback.json
    validation_report.json
    repair_log.json
  public/game/
    background/
    figure/
    bgm/
    scene/
      start.txt
      act1_xxx.txt
      ending_best.txt
```

## Function Tools 和 Schema

Function tools 源文件：

```text
webgal-game-function-call/references/openai-tools.json
```

API-ready 文件：

```text
webgal-game-function-call/references/openai-tools.built.json
```

重新构建：

```powershell
python webgal-game-function-call/scripts/build_openai_tools.py `
  webgal-game-function-call/references/openai-tools.json `
  webgal-game-function-call/references/openai-tools.built.json
```

Schema：

```text
narrative_plan.schema.json
asset_manifest.schema.json
scene_batch.schema.json
validation_report.schema.json
repair_plan.schema.json
```

## 设计原则

### LLM 只负责提出结构

LLM 输出必须经过：

```text
JSON parse -> JSON Schema -> semantic validation -> artifact write
```

### 后端负责流程推进

后端决定：

- 是否接受输出
- 是否写文件
- 是否进入下一阶段
- 是否触发 repair
- 是否 fallback

### 能确定性生成的部分尽量确定性生成

例如：

- WebGAL `.txt` 渲染
- validation
- scene fallback

这样可以降低长文本 JSON 被截断的风险。

## 常见问题

### `DEEPSEEK_API_KEY is not set`

通常是没有创建 `.env`。

解决：

```powershell
copy .env.example .env
notepad .env
```

### `emit_scene_batch returned invalid JSON arguments`

这是 DeepSeek 返回的 function arguments 被截断或拼坏。

当前系统已经加了 scene fallback。正常情况下不会因此终止任务，而是会生成：

```text
state/scene_generation_fallback.json
```

并继续写出 WebGAL scene 文件。

### Validation 失败

查看：

```text
state/validation_report.json
```

如果有 errors，pipeline 会尝试 repair。

## 快速命令

启动：

```powershell
.\start_backend.ps1
```

只跑 scenes：

```powershell
python -m webgal_backend.cli phase {job_id} scenes
```

重新 build tools：

```powershell
python webgal-game-function-call/scripts/build_openai_tools.py `
  webgal-game-function-call/references/openai-tools.json `
  webgal-game-function-call/references/openai-tools.built.json
```

编译检查：

```powershell
python -m compileall webgal_backend
```
