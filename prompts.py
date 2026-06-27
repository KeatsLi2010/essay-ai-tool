"""Prompt builders and Gaokao scoring guides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import trim_text


def previous_review_context(previous: dict[str, Any]) -> str:
    analysis = previous.get("analysis") if isinstance(previous.get("analysis"), dict) else {}
    analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2) if analysis else "无结构化批阅结果。"
    report_text = ""
    report_path = previous.get("report_path")
    if report_path:
        try:
            path = Path(str(report_path))
            if path.exists() and path.is_file():
                report_text = path.read_text(encoding="utf-8")
        except OSError:
            report_text = ""
    return f"""
上一稿批阅结果（结构化 JSON，仅用于第二阶段“修改分析”，不得用于第一阶段本稿独立评分）：
{trim_text(analysis_text, 12000)}

上一稿批阅报告正文（Markdown，仅用于第二阶段“修改分析”，不得用于第一阶段本稿独立评分）：
{trim_text(report_text, 12000) if report_text else "未找到上一稿批阅报告文件。"}
""".strip()

def assignment_messages(title: str, topic: str, writing_type: str) -> list[dict[str, str]]:
    system = """你是一位熟悉中国高考语文作文评价的作文教练。你擅长审题、辨析任务限制、拆解可能立意，并能区分微写作、大作文、记叙文、议论文、应用文等文体要求。必须输出严格 JSON，不要使用 Markdown。表达要简练，避免长段铺陈。"""
    user = f"""
请对一次作文作业做审题分析。输出 JSON，字段如下：
- assignment_type：优先参考“用户标注文体”判断任务类型，可写“思考类作业”“微写作”“大作文”或“不确定”；只有题目证据明显冲突时才修正，并说明依据。
- genre_candidates：可能文体与适配度，最多 4 项，每项 reason 不超过 25 字。
- core_task：题目真正要求学生完成的写作任务，不超过 80 字。
- constraints：显性与隐性限制，各不超过 5 条，每条不超过 25 字。
- thesis_options：4-6 个可选立意，每个只包含 keyword、angle、main_idea、genre、risk。keyword 不超过 6 字，angle 不超过 18 字，main_idea 不超过 42 字，risk 不超过 24 字。不要写长句，不要解释背景。
- best_thesis：你认为最稳且有上限的立意，字段包含 keyword、reason；reason 不超过 50 字。
- scoring_focus：按高考导向说明评分关注点。
- pitfalls：常见偏题、空泛、套作、价值风险，最多 5 条，每条不超过 30 字。
- teaching_notes：给老师的课堂提醒，最多 5 条，每条不超过 35 字。
- student_brief：给学生看的简短写作提示，不超过 100 字。

额外要求：
1. “可能立意”必须像表格条目一样短，不要写段落。
2. 每个立意只保留一个核心判断，风险只写最主要风险。
3. 语言务必适合快速扫读。
4. 用户标注文体是强提示：若标注为“思考”，assignment_type 应优先判为“思考类作业”，scoring_focus 应强调问题意识、思考过程、推理依据和自我反省，不要套用完整大作文结构要求。
5. 若用户标注文体为“微写作”“大作文”“记叙文”“议论文”“应用文”，任务类型和可能文体都要优先参考该提示；只有题目明确相反时，才写出修正理由。

作业标题：{title}
用户标注文体：{writing_type}
题目全文：
{topic}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


GAOKAO_NARRATIVE_RUBRIC = """
记叙文专项评分参考（60 分制，用于定档与解释；最终 score 使用 60 分满分）：
1. 基础等级 40 分：
   - 内容 20 分：一类 17-20，立意深刻、选材新颖、内容饱满、情感真挚、有独到观察；二类 13-16，立意明确、选材恰当、内容具体但亮点不足；三类 9-12，立意基本清楚但内容单薄；四类 5-8，偏题、空洞、情感虚假；五类 0-4，严重跑题或内容不成立。
   - 表达 20 分：一类 17-20，语言流畅精炼，记叙、描写、抒情、议论融合，结构严谨，节奏得当；二类 13-16，语言通顺，结构完整但特色不足；三类 9-12，表达单一、结构松散或套作明显；四类 5-8，病句较多、结构混乱；五类 0-4，语言极差，无法成篇。
2. 发展等级 20 分：从深刻、丰富、文采、创意四方面看。一类 17-20 至少两个方面突出；二类 13-16 至少一个方面较好；三类 9-12 有亮点但不突出；四类 5-8 整体平淡；五类 0-4 无明显特征。
3. 记叙文必须重点检查：是否有一个核心事件/场景，小中见大；是否有动作、语言、神态、心理、环境等细节支撑；情感是否真实克制；结构是否有线索、呼应、详略；开头是否入题，结尾是否有余味。
4. 判分纪律：严控一类文，50+/60 必须基础等级均一类且发展等级至少两个维度突出；流水账内容分不超过 12/20；明显套作或文体四不像总分最高不超过 40/60；假大空升华应降档；标题缺失扣 2 分，错别字最多扣 3 分，字数不足按题目要求谨慎扣分。
5. 微写作若题目明确要求短文、片段、应用场景，则不要机械套用 800 字大作文标准；仍需看任务完成度、文体适配、表达凝练度和现场感。
""".strip()


GAOKAO_STRICT_BANDING_GUIDE = """
高考作文严格定档总则（大作文统一按 60 分制评分）：
适用边界：本总则主要用于大作文和完整成篇作文；若任务类型为“微写作”，必须优先采用“微写作评分指南”，只保留 60 分档位一致性，不套用大作文篇幅、标题、完整结构和传统发展等级要求。
1. 总分档次：
   - 一类文：50-60 分。必须审题准确、中心突出，内容和表达均进入一类，发展等级至少两个维度突出。50-53 为一类低段，54-56 为一类中段，57-60 为一类高段。没有鲜明亮点、只是完整通顺，不得进入一类。
   - 二类文：40-49 分。审题基本准确，中心明确，结构完整，语言通顺，有一定材料或思考，但亮点不足、细节不够、思辨不深或表达平稳。40-43 为二类低段，44-46 为二类中段，47-49 为二类高段。
   - 三类文：30-39 分。基本完成题目，有中心但较浅，材料单薄或结构松散，语言基本通顺但问题较多。30-33 为三类低段，34-36 为三类中段，37-39 为三类高段。
   - 四类文：20-29 分。偏题较明显、内容空洞、结构混乱、语言问题较多，或文体任务完成很差。
   - 五类文：0-19 分。严重跑题、抄袭套作、残篇、无法成文、价值导向严重错误或内容不成立。
2. 分项定档：
   - 内容 20 分：看审题、立意、材料、中心、情感/观点。17-20 一类，13-16 二类，9-12 三类，5-8 四类，0-4 五类。
   - 表达 20 分：看结构、文体、语言、叙述/论证方式、书面规范。17-20 一类，13-16 二类，9-12 三类，5-8 四类，0-4 五类。
   - 发展 20 分：看深刻、丰富、文采、创意。17-20 至少两个维度突出；13-16 至少一个维度较好；9-12 有亮点但不突出；5-8 平淡；0-4 无发展特征。
3. 硬性上限：
   - 完全偏题或严重跑题：最高 25/60；若基本无关，最高 19/60。
   - 套作、宿构痕迹明显：最高 40/60；严重套作或疑似抄袭，最高 30/60。
   - 文体四不像或完全无视明确文体要求：最高 40/60；严重错文体且任务失败，最高 35/60。
   - 大作文不足 800 字：应说明字数风险；600-799 字原则上不进一类，600 字以下按残篇倾向处理，最高 35/60。
   - 标题缺失扣 2 分；错别字每个扣 1 分，重复不计，最多扣 3 分；病句、格式、标点等按表达或规范风险扣分。
   - 价值判断明显偏激、事实硬伤影响中心、虚假煽情严重：降档或设置上限。
4. 分数一致性：
   - 必须先给 total_60，最终 score 必须直接等于 total_60，不再换算成其他满分制。
   - grade_band 必须与 total_60 一致。例如 total_60=47 只能写二类高段，不能写三类或一类；score=47 也必须对应二类高段。
   - 不能出现“评语很高但分数低”或“分数很高但定档低”的矛盾；若有硬性上限，最终分数不得突破上限。
5. 判分纪律：
   - 不给鼓励性高分。完整、通顺、扣题只是二类基础，不自动进入一类。
   - 一类文必须有可指出的高分证据：独到立意、关键细节、结构设计、语言文采、思辨深度或材料新意。
   - 对优秀作文也要指出可改处，但不能因细小瑕疵过度压分；对普通作文不能因态度真诚而拔高。
""".strip()


GENRE_SCORING_GUIDE = """
评分前必须先区分文体，并按文体差异给分：
1. 记叙文/记叙性作文：看核心事件或场景、叙事取舍、细节密度、人物/情感真实度、线索呼应、结尾余味。没有核心事件、只有空泛感悟的，不可按高分记叙文处理。
2. 议论文/论述文：看中心论点是否明确，概念界定是否清楚，论证层次是否递进，材料与观点是否匹配，是否有反面辨析或边界意识，语言是否准确有力。堆例子、喊口号、只有感想没有论证的，应降档。
3. 记叙性议论文：既要有可感的叙事材料，也要有由事入理的思辨推进。若叙事和议论互相割裂，不能简单取两者优点加分。
4. 散文/抒情文：看意象统摄、情感脉络、语言节奏、虚实结合、内在逻辑。辞藻堆砌但中心松散的，应降档。
5. 应用文/任务驱动写作：看对象意识、情境任务、格式规范、交际目的、信息完整度和语言得体性。格式或对象意识严重缺失，要在结构文体和规范风险中扣分。
6. 微写作：看是否精准完成小任务，表达是否凝练，是否有现场感或观点密度；不要用大作文的篇幅、铺垫和升华标准机械要求。
7. 文体匹配纪律：若题目明确要求某文体而学生写成另一文体，应说明错位程度，并设置合理分数上限；严重“文体四不像”或完全无视文体任务，原则上不得进入高分档。
""".strip()


MICRO_WRITING_SCORING_GUIDE = """
微写作评分指南（60 分制，专门用于短评、片段、应用场景、小任务写作；优先于大作文篇幅和发展等级要求）：
1. 核心原则：微写作不是“大作文缩短版”。评分主轴是“任务完成度 + 扣材料/情境 + 表达凝练 + 观点或现场密度”。微写作天然篇幅有限，不能要求像大作文那样充分展开、铺陈论证、设置完整结构或升华；短而准、短而有力应被视为优点，不得因为篇幅短、无标题、没有完整开头结尾、没有铺垫升华而机械压分。
2. 推荐分项口径：
   - 内容/任务 20 分：是否完整回应指令，是否抓住关键词，是否扣住材料或情境，是否完成指定动作（如分析利弊、劝说、推荐、说明、描写片段）。17-20 为任务完成充分且抓点精准，哪怕论述很短也可以给高分；13-16 为基本完成但关键关系、材料扣合或对象意识有可见缺口；9-12 为只完成一部分、漏掉明确要求或扣题不紧；8 以下为明显漏任务或偏题。
   - 表达/文体 20 分：是否符合短评、片段、应用文、说明、描写等具体形式，语言是否清楚、简洁、得体，有无冗余、病句、对象意识缺失。微写作以凝练为优点，不能因没有大作文式文采而低估表达；语言通顺简洁通常不应低于 13/20。
   - 发展/亮点 20 分：重新理解为“观点密度、思辨层次、现场感、细节选择、信息组织、独到角度”，而不是大作文的铺陈、华丽文采或宏大升华。只要在有限篇幅内完成有效判断、关键辨析、具体扣材或有力表达，即可进入 13-16；有精准辨析、新鲜角度或高信息密度可进入 17+。不要以“还可以展开更多”为主要扣分理由。
3. 微写作总分档：
   - 50-60：任务完成很充分，观点/场景集中而有密度，语言简洁有力，材料或情境扣合紧。56+ 需要明显精准、漂亮或有独到思辨；但优秀短文可以进入 50+。
   - 40-49：任务基本完成，观点明确，结构清楚，语言通顺；主要问题应是关键扣材不够细、明确要求落实不完整、判断依据略弱或表达略平，而不是单纯“篇幅有限”。
   - 30-39：能看出任务意识，但漏掉关键要求、只写单面、材料结合弱、判断缺少依据或表达较粗疏。
   - 20-29：核心任务完成较差，明显偏离情境/对象，观点空泛，主要内容不能支撑判断。
   - 0-19：严重离题、残篇、无法理解、与任务基本无关。
4. 常见误扣纠正：
   - 不因“字数少于大作文”“篇幅有限无法展开”“没有题目”“没有三段式”“没有升华句”“修辞少”“韵律平直”直接降档；只有题目明确要求标题、格式或字数时才作为扣分依据。
   - 不把“内容单薄”“论证不充分”“展开不足”作为默认扣分语。只有当学生没有完成题目明确要求、关键概念关系没说清、材料/情境完全没有扣住，或判断缺少最低限度理由时，才可据此扣分。
   - 若题目要求“分析利弊/两面/比较/评价”，漏掉一面是任务完成度问题，可以明显扣分；但若两面都涉及且理由成立，即使篇幅短，也应按微写作高完成度评价。
   - score_breakdown 和 radar_scores 中，“语言表达、韵律节奏、结构层次、发展亮点”要按微写作的简洁、密度、短结构、短评力度理解，不能套用大作文的细节丰满、长线结构和文采发展等级。
5. 问题诊断与修改建议：微写作的建议应优先是“在原有篇幅中替换一句、补一个关键词、增加一个最关键依据、压缩一句空话换成具体扣材”，而不是要求大段扩写。若确需补充，也要说明“用一句话补足”。
6. 输出要求：detected_task_type 为“微写作”时，gaokao_60_reference 和 strict_gaokao_banding 必须说明采用微写作口径；final_band_reason 要解释分数来自任务完成度、扣材/情境、表达凝练和观点密度，而不是传统大作文篇幅或展开充分程度。
""".strip()


THINKING_SCORING_GUIDE = """
“思考”类作业单独处理，不按高考大作文的记叙文/议论文完整成篇要求硬套。
1. 核心评价对象：问题意识、真实经验、思考过程、推理链条、自我反省、边界意识、具体发现和后续行动可能。
2. 可以忽略或弱化的角度：华丽语言、完整三段式结构、文采发展等级、叙事详略、开头结尾升华等，不把这些作为主要扣分点。
3. 仍需保留的底线：必须回应题目或任务；不能只有情绪宣泄、空泛表态、口号堆叠；关键判断要有经验、现象或理由支撑；表达应基本清楚。
4. 评分建议：优先看“是否真的想过”。高分思考应有明确问题、具体触发点、推理推进、反证或自我修正、可迁移的结论；中档思考有真实感但停留在感想；低档思考空泛、混乱或离题。
5. 输出兼容要求：仍输出 score、score_breakdown、radar_scores、strict_gaokao_banding 等字段，但“语言表达、结构层次、发展亮点、韵律节奏”只作辅助观察；不要因语言朴素、结构不工整而机械压分。
6. score_breakdown 和 radar_scores 中，重点权重应落在“审题立意、内容材料、文体适配、规范表现”；结构、语言、韵律、发展可给出温和评价，并明确“非主要评分依据”。
7. strict_gaokao_banding 可以沿用 60 分档位，但 final_band_reason 必须说明这是思考类作业，定档依据主要来自思考质量，而非传统作文的文采、结构或发展等级。
8. issues 中的问题诊断应优先指出：问题不够清楚、判断缺少依据、推理跳步、自我反省不足、只表态不分析、经验与结论脱节等；少用“结构松散、语言平淡、发展不足”作为核心问题。
""".strip()


def submission_messages(
    assignment: dict[str, Any],
    content: str,
    previous: dict[str, Any] | None,
    revision_hint: bool,
) -> list[dict[str, str]]:
    writing_type_hint = str(assignment.get("writing_type_hint") or "").strip()
    assignment_analysis_data = assignment.get("analysis", {}) if isinstance(assignment.get("analysis"), dict) else {}
    assignment_type_text = str(assignment_analysis_data.get("assignment_type") or assignment_analysis_data.get("detected_task_type") or "")
    is_thinking = writing_type_hint == "思考"
    is_micro = writing_type_hint == "微写作" or "微写作" in assignment_type_text
    system = """你是一位严格、细致、但会保护学生写作信心的写作评分教师。你必须把分数统一使用 60 分满分。普通高考作文按高考作文标准评价；若作业文体提示或审题分析表明是“微写作”或“思考”，必须分别按微写作/思考类作业单独处理，不要硬套传统大作文的篇幅、语言、结构、发展等级。必须输出严格 JSON，不要使用 Markdown。"""
    previous_text = ""
    if previous:
        previous_text = f"""
上一稿信息：
submission_id：{previous.get("id")}
上一稿分数：{previous.get("score")}
上一稿正文：
{trim_text(previous.get("content", ""), 10000)}

{previous_review_context(previous)}
"""
    assignment_analysis = json.dumps(assignment.get("analysis", {}), ensure_ascii=False)
    thinking_mode_note = (
        "本次作业文体提示为“思考”。请启用下方“思考类作业评分指南”，把思考质量作为主轴；语言、结构、发展、韵律只作辅助观察，不作为主要扣分依据。"
        if is_thinking
        else "本次作业不是“思考”类，按题目期待文体和高考作文标准评分。"
    )
    micro_mode_note = (
        "本次作业按“微写作”处理。请启用下方“微写作评分指南”：以任务完成度、扣材料/情境、表达凝练和观点/现场密度为主；篇幅有限导致无法充分展开是微写作常态，不得机械套用大作文篇幅、标题、完整结构、论证铺陈、文采升华或发展等级要求。"
        if is_micro
        else "本次作业未被预判为微写作；若题目或正文显示它实际是短评/片段/应用场景小任务，再按微写作评分。"
    )
    user = f"""
请评判下面这篇学生作文。输出 JSON，字段如下：
- detected_task_type：优先参考“作业文体提示”判断任务类型，可写“思考类作业”“微写作”“大作文”；只有学生正文或题目证据明显冲突时才修正，并说明依据。
- expected_genre：根据题目和作业审题分析判断题目期待或允许的文体；如果多文体均可，列出主次。
- detected_genre：判断实际文体，如记叙文、议论文、记叙性议论文、应用文等。
- genre_evidence：引用原文或题目特征，说明为什么这样判断文体。
- genre_fit：文体与题目要求是否匹配，明确写“匹配 / 基本匹配 / 部分错位 / 明显错位 / 文体四不像”。
- genre_specific_assessment：按该文体专项标准评价，不同文体必须使用不同关注点。
- genre_score_cap：如文体错位或文体四不像，说明建议分数上限；如无上限问题，填 null。
- score：0-60 的整数总分，必须与 strict_gaokao_banding.final_total_60 一致。
- score_breakdown：60 分制分项说明，必须包括“审题立意、文体适配、内容材料、结构层次、语言表达、韵律节奏、发展亮点、规范风险”，总分口径需与 score 一致。
- radar_scores：八方面雷达图数据，必须是对象，键固定为“审题立意、文体适配、内容材料、结构层次、语言表达、韵律节奏、发展亮点、规范表现”，每项为 0-20 的数字；“规范表现”越高表示越规范、风险越低。
- gaokao_60_reference：必须给出 60 分制参考，包括 total_60、content_20、expression_20、development_20、band_reason；大作文按高考作文三项，微写作按“内容/任务、表达/文体、发展/密度”重新解释。
- strict_gaokao_banding：严格定档结论，必须包含 content_band、expression_band、development_band、initial_total_band、hard_caps、penalties、final_total_60、final_band_reason；微写作的三个 band 必须按微写作口径解释；不要输出 converted_score_100 或 consistency_check。
- grade_band：按 total_60 写明高考档次，如“一类低段/二类高段/三类中段”等，必须与 strict_gaokao_banding.final_total_60 一致。
- overall_comment：总评。
- strengths：亮点列表。
- issues：问题列表，每项包含 quote、problem、reason、suggestion。
- language_rhythm：语言、句式、节奏、韵律、文气分析。
- revision_plan：按优先级给出可执行修改建议。
- score_raise_path：如果要提高 5-10 分，最该改什么。
- style_observation：这篇文章体现的个人语言风格。
- revision_analysis：如果是修改稿或存在上一稿，必须作为重点分析，结构化输出；如果是初稿，填 null。结构如下：
  {{
    "overall": "一句话评价本次修改的整体质量",
    "score_change_reason": "说明分数变化与修改的关系；无明显变化也要解释原因",
    "previous_review_response": "概括本稿回应上一稿批阅结果的情况：哪些问题已解决，哪些建议未落实，哪些扣分原因仍存在",
    "changes": [
      {{
        "change_type": "立意/结构/材料/细节/语言/文体/结尾/其他",
        "review_basis": "对应上一稿批阅中的问题、修改建议或扣分原因；如无法对应则写 null",
        "before": "上一稿相关原文或概括",
        "after": "本稿对应原文或概括",
        "what_changed": "具体改了什么",
        "effect": "这样改为什么好或为什么不好",
        "evidence": "引用或概括能证明修改效果的文本证据",
        "remaining_issue": "仍需继续改的地方；没有则写 null"
      }}
    ],
    "new_problems": ["如修改带来新问题，逐条写；没有则空数组"],
    "keep_next_time": ["下次应保留的有效修改策略"]
  }}
- teacher_note：给老师的简短备注。

评分要求：
0. 修改稿必须采用“两阶段判分”：第一阶段只看题目、作业审题分析、本稿正文，独立完成文体判断、问题诊断、严格定档和 score；这一阶段不得参考上一稿分数、上一稿批阅结果或上一稿报告。第二阶段才读取上一稿正文与上一稿批阅结果，专门生成 revision_analysis，用来解释修改质量、回应旧问题的程度、分数变化原因和新问题。最终 score 以第一阶段独立评分为准，不得因为上一稿分数、上一稿评价高低或上一稿扣分点而直接上调或下调。
1. 必须严格按 60 分制定档：先给出 total_60；最终 score 必须直接等于 total_60。大作文按高考作文定档；微写作按“微写作评分指南”定档，不得套用 800 字大作文要求。
2. 必须先参考“作业文体提示”判断任务类型和题目期待文体，再判断学生实际文体；文体提示要影响评分，而不是只作标签。若与题目或正文明显冲突，必须说明为什么修正。
3. 若实际文体为记叙文、记叙性议论文或以叙事为主体，必须参考下方“记叙文专项评分参考”定档，严控一类高分。
4. 若题目明确要求某文体而作文写成另一文体，必须在 genre_score_cap 和 score_breakdown 的“文体适配”中扣分。
5. 必须说明微写作与大作文的评价重点差异。若 detected_task_type 为“微写作”，score、gaokao_60_reference、strict_gaokao_banding、score_breakdown、radar_scores 都必须采用微写作口径；不得把“篇幅短小、篇幅有限无法充分展开、没有标题、缺少铺垫升华、文采不足、韵律平直”作为主要扣分理由。不要把“可进一步展开”写成降档核心理由，除非它实际导致题目明确任务未完成。
6. 要把“语言”和“韵律节奏”作为独立观察对象，不能只说流畅。
7. 修改稿的 revision_analysis 必须同时参考“上一稿正文”和“上一稿批阅结果”：判断本稿是否回应了上一稿批阅中的主要问题、修改建议、扣分原因，再比较前后稿，评价修改是否有效；修改分析的重要性与问题诊断相同，至少列出 3 条具体修改（若实际修改不足 3 条，说明“可识别修改不足”），每条都要有 before、after、what_changed、effect、evidence，并尽量说明它对应上一稿批阅中的哪条问题或建议。初稿不需要硬凑修改分析。
8. 对异常价值判断、事实硬伤、套话、疑似套作要谨慎提示，但不要武断定性。
9. 问题诊断必须引用原文短句，并给出可执行修改建议。
10. 严禁分数与档次矛盾：例如 48/60 只能对应二类高段，不能写三类或一类。
11. 若作业文体提示为“思考”，detected_task_type 必须优先写“思考类作业”；不要机械套用语言、结构、发展、韵律等传统作文角度；请按“思考类作业评分指南”定档，并在文体专项评价、总评、问题诊断和定档理由中说明“思考质量”如何决定分数。
12. 若作业文体提示为“微写作”或作业审题分析 assignment_type 为“微写作”，detected_task_type 必须优先写“微写作”；只有题目和正文证据明显相反时才修正。微写作中的 development_band 不等于传统大作文“发展等级”，而是观点密度、扣材深度、现场感、信息组织或短评力度；不能因没有宏大升华或篇幅有限未充分展开而压到低档。

高考严格定档总则：
{GAOKAO_STRICT_BANDING_GUIDE}

文体区分与专项评分指南：
{GENRE_SCORING_GUIDE}

微写作评分指南：
{MICRO_WRITING_SCORING_GUIDE}

记叙文专项评分参考：
{GAOKAO_NARRATIVE_RUBRIC}

思考类作业评分指南：
{THINKING_SCORING_GUIDE}

作业标题：{assignment.get("title")}
作业文体提示：{writing_type_hint or "auto"}
本次评分模式提示：{thinking_mode_note}
微写作评分模式提示：{micro_mode_note}
题目全文：
{assignment.get("topic")}

作业审题分析：
{trim_text(assignment_analysis, 8000)}

是否按修改稿处理：{revision_hint}
{previous_text}

学生作文：
{trim_text(content, 16000)}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def revision_analysis_messages(
    assignment: dict[str, Any],
    content: str,
    previous: dict[str, Any],
    independent_analysis: dict[str, Any],
) -> list[dict[str, str]]:
    system = """你是一位作文修改分析教师。你只负责分析修改稿相对上一稿的变化，不负责重新评分。必须输出严格 JSON，不要使用 Markdown。"""
    user = f"""
请只生成 revision_analysis，不要修改、质疑或重新给出本稿分数。

重要边界：
1. 本稿分数已经由另一次独立评分完成；那次评分没有看到上一稿分数、上一稿批阅或上一稿报告。
2. 你现在可以参考上一稿正文、上一稿批阅结果和本稿独立评分结果，但只能用于解释“修改质量”和“是否回应旧问题”。
3. 不得输出新的 score、final_total_60、grade_band 或 strict_gaokao_banding；不得建议改动本稿独立分数。
4. 若提到分数变化，只能解释可能原因，不能把上一稿分数作为本稿评分依据。

输出 JSON 格式：
{{
  "revision_analysis": {{
    "overall": "一句话评价本次修改的整体质量",
    "score_change_reason": "说明本稿独立分数与修改质量的关系；无明显变化也要解释原因",
    "previous_review_response": "概括本稿回应上一稿批阅结果的情况：哪些问题已解决，哪些建议未落实，哪些扣分原因仍存在",
    "changes": [
      {{
        "change_type": "立意/结构/材料/细节/语言/文体/结尾/其他",
        "review_basis": "对应上一稿批阅中的问题、修改建议或扣分原因；如无法对应则写 null",
        "before": "上一稿相关原文或概括",
        "after": "本稿对应原文或概括",
        "what_changed": "具体改了什么",
        "effect": "这样改为什么好或为什么不好",
        "evidence": "引用或概括能证明修改效果的文本证据",
        "remaining_issue": "仍需继续改的地方；没有则写 null"
      }}
    ],
    "new_problems": ["如修改带来新问题，逐条写；没有则空数组"],
    "keep_next_time": ["下次应保留的有效修改策略"]
  }}
}}

要求：
1. 修改分析的重要性与问题诊断相同，至少列出 3 条具体修改；若实际修改不足 3 条，说明“可识别修改不足”。
2. 每条修改都要有 before、after、what_changed、effect、evidence，并尽量说明对应上一稿批阅中的哪条问题或建议。
3. 微写作修改建议应尊重篇幅限制，优先说明“替换一句、补关键词、加关键依据、压缩空话”等短文本修改策略。

作业标题：{assignment.get("title")}
题目全文：
{assignment.get("topic")}

本稿独立评分结果（不可更改，只作修改分析背景）：
{trim_text(json.dumps(independent_analysis, ensure_ascii=False, indent=2), 10000)}

上一稿信息：
submission_id：{previous.get("id")}
上一稿分数：{previous.get("score")}
上一稿正文：
{trim_text(previous.get("content", ""), 10000)}

{previous_review_context(previous)}

本稿正文：
{trim_text(content, 16000)}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def assignment_summary_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    system = """你是一位资深语文教师和写作教研组长。你要根据一次作业下目前所有学生提交与评分报告，生成面向教师的作业总结。必须输出严格 JSON，不要使用 Markdown。"""
    user = f"""
请为这次作业生成总结。输出 JSON，字段如下：
- overall：本次作业整体完成情况，120 字以内。
- score_distribution：分数分布与档位观察，指出高分、中段、低分的大致特点。
- task_understanding：学生对题目、任务类型、文体提示的理解情况。
- common_strengths：共性亮点列表，每条包含 point、evidence、students。
- common_issues：共性问题列表，每条包含 issue、reason、typical_students、teaching_fix。
- student_notes：逐个学生简短备注，数组项包含 student、versions、score、main_strength、main_issue、next_step。
- revision_observations：如果有修改稿，概括修改质量；没有则写“暂无明显修改稿样本”。
- radar_observations：结合八方面雷达数据概括优势与短板；没有则写 null。
- teaching_actions：下一次讲评或训练建议，3-6 条，务必可执行。
- next_assignment_suggestions：后续作业设计建议，2-4 条。

要求：
1. 这是“作业总结”，不是单篇评分；不要重复每篇完整报告。
2. 必须覆盖当前提交列表中的所有学生，但逐个学生备注要简短。
3. 如果同一学生有多版提交，要指出终稿表现与修改趋势。
4. 表达适合教师快速扫读，避免空话。

数据如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def style_messages(student_payload: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = """你是一位擅长学生写作风格追踪的语文教师。你需要从历次作文中归纳语言风格，并找出可能异常的作业。异常只作为教学提醒，不等于作弊判定。必须输出严格 JSON，不要使用 Markdown。"""
    user = f"""
请分析这些学生的历次作文。输出 JSON，字段如下：
- students：数组。每个学生包含 student、style_profile、per_assignment_styles、style_baseline、development、score_pattern、possible_anomalies、next_training。
- per_assignment_styles：逐篇列出该学生每次写作的风格，数组每项包含 submission_id、assignment、version_no、style_summary、language_rhythm_summary、genre_style、stable_features、new_or_changed_features、evidence。
- style_baseline：只从该学生多次作文中反复出现的特征归纳稳定基线；如果只有一篇，写“样本不足，暂不建立稳定基线”。
- possible_anomalies：必须把可疑作业与该学生自己的 style_baseline 和前后相邻作文对比；每项包含 submission_id、anomaly_level（正常/轻微偏离/明显偏离/需复核）、compared_with、deviation_points、evidence、alternative_explanation、confidence。
- cross_student_notes：不同学生风格差异与教学提醒。
- caution：说明异常识别的局限。

判定要求：
1. 必须先逐篇概括每次作文风格，再归纳个人稳定风格基线，最后才判断异常。
2. 判断异常时只能与“同一学生”的历次作文、单篇 style_observation、language_rhythm、文本指标和原文片段对比；不要拿其他学生当异常标准。
3. 如果学生只有 1 篇作文，不得判定风格异常，只能提示“样本不足”。
4. 异常线索可包括：语言风格突然变化、句长/段落/文体显著变化、分数突升突降、与该生过往常用表达差异大、修改稿改动质量异常、内容成熟度突然不合常态等。
5. 每个异常判断必须给出证据和可能的正常解释，例如换题材、换文体、认真修改、教师指导、时间间隔变化；必须使用“可能”，不要武断。
6. 不要只输出总评，必须让老师看得出“每个人每次作文是什么风格，以及这次和之前哪里不同”。

数据如下：
{json.dumps(student_payload, ensure_ascii=False, indent=2)}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
