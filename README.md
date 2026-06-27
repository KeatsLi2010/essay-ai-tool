# 作文 AI 工具

这是一个本地 Python CLI，用 DeepSeek API 做作文作业管理、审题分析、作文评分、修改稿比较、得分曲线和语言风格异常提示。

工具使用标准库实现，不需要安装第三方包。默认模型名是 `deepseek-v4-pro`，API base 是 `https://api.deepseek.com`。

## 0. 启动网页 UI

在工具目录运行：

```powershell
cd "C:\path\to\essay_ai_tool"
python web_app.py
```

启动后浏览器打开：

```text
http://127.0.0.1:8765
```

如果 `8765` 被占用，程序会自动顺延到下一个可用端口，并在终端打印实际地址。

网页 UI 支持：

- 保存 DeepSeek API key、模型名和 API base
- 新建作文作业并生成审题分析
- 添加学生提交，区分初稿/修改稿，并转入后台评分任务
- 明确显示题目期待文体、学生实际文体、文体匹配情况和文体错位分数上限
- 生成学生得分曲线
- 生成语言风格与异常作业分析
- 对某次作业或某个学生的某次提交进行定向删除
- 删除和恢复上一步操作前都会弹出确认框

提交作文后，网页会立即返回，不会等待 AI 评分完成。此时作业仍可查看，最近提交表会显示“排队中 / 评分中”；分数和报告按钮会等后台评分完成后自动出现。评分失败时会显示“评分失败”，可查看提示后重新提交。

报告预览会把 `quote / problem / reason / suggestion / priority` 等结构字段渲染成批阅卡片、颜色标签和引用框，不再直接显示成生硬字段列表。

删除不会直接擦掉本地原文/报告文件，而是先从工具的数据索引中移除；误删时可以用“恢复上一步”找回记录。

## 1. 配置 API key

在工具目录运行：

```powershell
cd "C:\path\to\essay_ai_tool"
python essay_tool.py config-key
```

按提示粘贴 DeepSeek API key。它会保存在本目录 `.env`，并已被 `.gitignore` 忽略。

也可以临时设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

如果 DeepSeek 后续调整模型名，运行命令时加 `--model 新模型名`，或修改 `.env` 里的 `DEEPSEEK_MODEL`。

## 2. 新建一次作文作业

把作文题目保存为 `topic.txt`，然后运行：

```powershell
python essay_tool.py assignment-new --title "成长词语" --topic-file topic.txt
```

也可以直接传题目：

```powershell
python essay_tool.py assignment-new --title "成长词语" --topic "题目全文..."
```

工具会保存题目，并生成审题分析，包括可能文体、核心任务、多个立意、推荐主旨、评分关注点和常见风险。

## 3. 添加学生提交并评分

把作文正文保存为 `ytz.md`，然后运行：

```powershell
python essay_tool.py submission-add --assignment 作业ID --student ytz --content-file ytz.md
```

如果是修改稿：

```powershell
python essay_tool.py submission-add --assignment 作业ID --student ytz --content-file ytz-v2.md --revision
```

如果同一学生同一作业已有提交，工具默认会按修改稿处理，并比较上一稿：做了哪些修改、这些修改好不好、是否产生新问题。

如果要导入人工分数，或在离线测试时给作文一个分数，可以加：

```powershell
python essay_tool.py submission-add --assignment 作业ID --student ytz --content-file ytz.md --manual-score 52
```

评分统一为 `60` 分满分，报告会特别检查：

- 是否审准题、是否偏题
- 题目期待文体和学生实际文体是否一致
- 文体是微写作还是大作文，是记叙文、议论文、记叙性议论文、散文还是应用文
- 按不同文体使用不同评分重点，而不是套用同一套话术
- 内容材料、结构、语言表达
- 句式、节奏、韵律、文气
- 高考导向下的价值边界和事实风险
- 可执行修改建议与提分路径

评分会按高考作文 `60` 分制直接定档和统计：

- 一类文：`50-60 / 60`
- 二类文：`40-49 / 60`
- 三类文：`30-39 / 60`
- 四类文：`20-29 / 60`
- 五类文：`0-19 / 60`

报告会单独显示“严格定档依据”，包括内容/表达/发展等级、硬性上限、扣分项、最终 `60` 分和定档理由。系统会要求 AI 避免“分数高但档次低”或“档次高但分数低”的矛盾。

如果文体明显错位，报告会单独写出“文体分数上限提示”，并在 `score_breakdown` 的“文体适配”中扣分。

如果作文适合按记叙文或记叙性作文评价，工具会让 AI 同时给出一个 `60` 分制参考分项：

- 基础等级——内容：`20` 分
- 基础等级——表达：`20` 分
- 发展等级：`20` 分
- 定档理由：对照一类文、二类文等高考作文档次

这个 `60` 分制分数同时用于批阅解释、统计曲线和学生追踪。

## 4. 生成得分曲线

```powershell
python essay_tool.py curves
```

只看某个学生：

```powershell
python essay_tool.py curves --student ytz
```

会生成 Markdown 分析报告和 SVG 曲线图。

## 5. 分析语言风格与异常作业

```powershell
python essay_tool.py style-report
```

只分析某个学生：

```powershell
python essay_tool.py style-report --student ytz
```

报告会归纳每个学生的语言风格、发展趋势、分数变化，并提示可能异常的作业。异常只是教学复核线索，不等于作弊或代写判定。

## 6. 查看与撤销

查看作业：

```powershell
python essay_tool.py list assignments
```

查看学生：

```powershell
python essay_tool.py list students
```

撤销上一次新增作业、学生提交、曲线报告或风格报告：

```powershell
python essay_tool.py undo
```

撤销会恢复上一步之前的 `state.json`，并删除那一步新建的报告/正文文件。

## 7. 离线测试

没有 API key 时，可以用 `--no-ai` 先测试保存、曲线、撤销流程：

```powershell
python essay_tool.py assignment-new --title "测试作业" --topic "请以慢为题作文。" --no-ai
python essay_tool.py submission-add --assignment 测试作业 --student abc --content "这是一篇测试作文。" --no-ai
python essay_tool.py undo
```
