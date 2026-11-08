# 短剧生成平台的用户旅程（调研，2026-11）

> 目的：对照主流 AI 短剧平台的创作流程，决定 Jellyfish 创作页接下来「复刻」什么。
> 来源以厂商页面与第三方评测为主，带宣传成分；功能细节以各平台当前版本为准。

## 调研对象

| 平台 | 定位 | 流程骨架 |
| --- | --- | --- |
| LibTV（哩布 TV，LiblibAI） | 一站式 AI 短剧平台，无限画布 + 节点工作流，另有 Agent「一句话出片」入口 | 剧情描述 / 上传剧本 → 剧本解析、优化 → 角色 / 场景 / 道具自动提取为独立资产卡片（三视图、多角度、一致性管理）→ 按脚本批量生成分镜图（多机位九宫格、多帧）→ 接可灵 / Seedance 生视频（灯光、相机、运镜、精准编辑）→ 同一画布预览成片 |
| 即梦「短剧工作室」（剪映 / 字节） | 剧本、导演、剪辑放进同一个工作室 | DreamScript 剧本模型（上传 ≤10 万字，拆人物 / 场景 / 冲突，「剧本医生」）→ 识别人物与场景并生成角色设定 + 提示词供确认 → 生成角色 / 场景资产并关联分镜 → 3D 导演台摆机位 / 运镜，智能预演串联关键镜头，低成本「白模参考」检查动作 → 生视频 → 后期 |
| LTX Studio（Lightricks） | storyboard-first 的影视前期制作管线 | 上传剧本 → AI 拆 scenes / shots → 角色、物件、场景抽成可复用 Elements（可上传参考、选风格）→ 先在故事板上确认每个镜头（机位、角色外观、模型可换）→ 逐镜生成，坏的单独重生成 → 时间线剪辑（转场、音效）→ 导出 MP4 评审 |
| Pixmax / SkyReels / 剧大虾 / 短剧 AI 等 | 国内一站式短剧工具 | 故事大纲 → 角色设定 + 参考图 → 分镜画面 → 视频片段 → 配音（按角色音色）→ 字幕 → 合成导出；强调系列剧的人物一致 |
| 可灵 / Vidu / 海螺 | 更接近「生成器」 | 单段画面与运镜质量强；角色库、分镜脚本、整集合成一般要配合其它工具（评测结论不一致，以官网为准） |

## 共性旅程（抽象）

1. **剧本**：粘贴 / 上传 / 一句话让 AI 写；平台解析出人物、场景、冲突，并给出可编辑的拆解结果。
2. **资产库**（角色 / 场景 / 道具）：自动提取为卡片 → 每张卡有「设定描述 + 生成提示词」可改 → 生成形象（多视图）或**上传参考图** → 可手动新增 / 删除 / 合并 → 跨集复用。
3. **分镜脚本**：每镜一行 / 一卡，字段固定（景别、机位、运镜、画面描述、台词、时长）→ 引用资产（谁在画面里）→ 生成关键帧（可改提示词、重绘、多候选选一张、上传替换）→ 低成本预演。
4. **视频**：逐镜生成，模型 / 运镜可选，失败或不满意的单独重生成，多版本比较。
5. **后期**：配音（按角色音色）、字幕、BGM / 音效、转场 → 时间线 → 导出 / 分享评审。
6. **捷径**：Agent「一句话出整集」，把 1–5 全自动跑完再让人修。

## 对照 Jellyfish 创作页（2026-11-07）

| 阶段 | 平台做法 | Jellyfish 现状 | 差距 → 处理 |
| --- | --- | --- | --- |
| 剧本 | 写 / 改 / 解析 | 粘贴 + 一键拆分镜 | 「一句话 → AI 写剧本」「剧本医生」列入 P3 |
| 资产库 | 卡片可编辑、可上传、可改提示词、可新增、跨集复用 | 只能看与「生成形象」 | **P2 已做**：编辑名称 / 设定、看并改提示词再生成、上传图作形象、新增角色 / 场景 / 道具、设置出现镜头、其它集资产列出可沿用 |
| 分镜 | 固定字段 + 引用资产 + 关键帧可改可换 | 标题 / 描述 / 时长、生成 / 重画 | **P2 已做**：景别 / 运镜、画面里用到谁（可改）、对白增删改、上传关键帧；多候选选一张列入 P3 |
| 视频 | 逐镜、重试、多版本 | 逐镜、失败重试、真人参考自动改文字 | 多版本比较列入 P3 |
| 后期 | 配音 / 字幕 / BGM / 时间线 / 导出 | 连播 + 逐段下载 | 合成导出、TTS 配音、字幕列入 P3 |
| 捷径 | 一句话出整集 | 无 | 列入 P3（后端任务链已具备） |

## 第二轮细看：Higgsfield、LibTV、即梦（Seedance 自家）与 Seedance 2.x API（2026-11-07）

### Higgsfield（Popcorn 故事板 + Cinema Studio + Soul ID）

- **先拍故事板，再花钱生视频**：官方指南把流程定为「拆场 → 拆视觉节拍 → 每个节拍定景别 / 机位 / 运镜 / 目的 → 每个节拍出一张参考帧 → 锁定后进 Cinema Studio 生视频」，理由是「故事板阶段是整条流水线里犯错最便宜的地方」。
- **Shot list 是一张表**：列为 场次 / 镜号 / 景别 / 运镜 / 参考（角色 / 场景 / 服装 / 道具）/ 备注（意图 + 连续性要求，如「脸和外套与 1A 一致」）。
- **Popcorn 一次生成一组连贯帧**：最多 8 帧按「一个序列」生成（而非逐帧），角色、光线、空间关系在帧之间保持；每次最多 4 张参考（角色肖像 + 场景 + 服装 + 道具）；有手动 / 自动两种模式；跨组生成时「把已确认的最佳帧当参考」以减少漂移。
- **相机参数化**：Cinema Studio 用可选的运镜预设（crash zoom / dolly / crane / FPV / bullet time 等，可叠加）代替用文字描述相机；Soul ID 用 20+ 张照片训练角色身份；Lipsync Studio 做对口型。
- **提示词公式**：景别 + 运镜 + 主体 + 动作 + 场景 + 光线风格 + 参考。

### LibTV（哩布）

- **无限画布 + 五种节点**（文本 / 图片 / 视频 / 音频 / 脚本），上游输出即下游输入；每次生成**派生新节点而不覆盖原图**（非破坏性，可回退）。
- **图片节点自带相机控制**（相机类型、镜头、焦距、光圈）和一整套编辑（一键高清、扩图、局部重绘、擦除、抠图、多角度生成、打光调节），还有「标记」把多张图里的元素融合。
- **「/」隐藏工具**：多机位九宫格、剧情推演四宫格、25 宫格连贯分镜、电影级光影校正、角色三视图、画面推演（3 秒后 / 5 秒前）。宫格是一整张图，可切成独立帧再喂给视频节点当参考——用一次图片生成的钱先验证整段节奏。
- **视频在站内裁剪**、自动配乐 + 剪辑成片；顶级模型（可灵 / Seedance 等）自由选；Agent 通过 Skill「一句话出片」。

### 即梦短剧工作室（Seedance 自家产品）

- **三种入口**：一句话原创 / IP 改编 / 上传已有剧本。原创走 DreamScript：选国内 / 出海、集数（10–100）、受众、人设标签、画面风格 → 给 3 个故事方向 → 完整故事设定、分集大纲、完整剧本；「剧本医生」做诊断。
- **资产化**：剧本解析出角色、场景与出场关系，先生成「角色设定 + 生成提示词」让人确认，再由面向短剧美术调校的 Anycook 模型出图；同一角色可有多种形态资产并标注出现集数；资产跨集 / 续集沿用；镜头提示词里用引用标记绑定资产形象。
- **3D 导演台 + 智能预演**：在三维空间摆站位、道具、机位和运动轨迹，白模预演不消耗视频算力，预演结果作为「动态参考」进视频节点再换成正式人物服装。
- **片段重拍 + 超分**：只重拍不满意的几秒，不整集重跑。

### Seedance 2.x API 能力（ModelArk，我们现在用的就是它）

| 能力 | 2.0 | 2.5 | Jellyfish 现状 |
| --- | --- | --- | --- |
| 全能参考（omni-reference） | 图 ≤9、视频 ≤3（仅 URL，合计 ≤15 s）、音频 ≤3（需配图 / 视频） | 图 ≤30、视频 / 音频 ≤10，合计 ≤30 s，支持纯音频驱动 | 只用 1 张首帧（`first`）或纯文字；角色 / 场景形象图没有进视频模型 |
| 引用语法 | 提示词里写 `[Image 1] …; [Video 1] 运镜; [Audio 1] 配乐`，按媒体类型各自从 1 编号 | 同 | 无 |
| 多镜头 | 时间码分段：`[0-4s]: 远景建立; [4-8s]: 推近` | 同，时长 4–30 s | 一镜一段文字；`ShotDetail.action_beats` 已有数据但没用到 |
| 模式互斥 | 首帧 / 首尾帧 与 全能参考不能混用 | 同 | — |
| 体积 | 请求体 ≤64 MB，大文件建议传 URL 而非 base64 | 同 | 现在全部 base64 内联；参考图一多就会超 |
| 真人人脸 | 普通上传含真人脸会被拒，需走人像资产通道 | 同 | 已映射为中文提示并自动改纯文字 |

### 可借鉴清单（按性价比排序）

| # | 借鉴点 | 来源 | 对 Jellyfish 的改动 | 预估 |
| --- | --- | --- | --- | --- |
| 1 | **全能参考生视频**：把镜头关联的角色形象图、场景参考图（+ 可选关键帧）作为 `reference_image` 一起喂给 Seedance，提示词用 `[Image n]` 点名「谁是谁」 | Seedance API、即梦资产引用、Higgsfield 4 参考 | 新增 `reference` 参考模式：契约加 `reference_images`、payload 走 URL 而非 base64、视频提示词模板生成 `[Image n]` 映射；确认单显示「形象参考 N 张」 | 1 天 |
| 2 | **时间码分镜段落**：一个镜头多个动作节拍时，提示词写成 `[0-3s] … [3-6s] …` | Seedance 多镜头、Higgsfield 节拍表 | 用已有 `action_beats` 自动分配时间段写进视频提示词；分镜抽屉可编辑节拍 | 0.5 天 |
| 3 | **视频提示词可见可改 + 上传自己的视频片段** | LibTV 节点可上传、即梦片段重拍 | 视频步骤每镜「查看 / 编辑提示词」「上传视频」 | 0.5 天 |
| 4 | **多候选选一张 + 非破坏性历史**：关键帧 / 形象图一次出 2–4 张，选一张采用；旧版本可回退 | LibTV 派生节点、Higgsfield variants | 图片任务返回多张；`ShotFrameImage` 增加候选表或用任务结果保存历史；卡片上「换一张 / 回退」 | 1–2 天 |
| 5 | **相机参数化预设**：运镜预设库（推 / 拉 / 摇 / 跟 / 环绕 / 手持…）+ 镜头焦段，写成固定句式进提示词 | Higgsfield Cinema Studio、LibTV 相机控制 | 分镜抽屉的景别 / 运镜扩成「预设 + 焦段」，提示词模板按公式拼 | 0.5 天 |
| 6 | **角色多视图**：从主形象派生正 / 侧 / 背三视图，作为 2–3 张参考一起进视频 | LibTV 三视图、即梦多形态资产 | 形象图行已有 `view_angle`；加「生成三视图」任务（Seedream 多图编辑） | 1 天 |
| 7 | **一句话 → 剧本**：题材 / 受众 / 集数标签 → 3 个故事方向 → 分集大纲 → 剧本；「剧本医生」 | 即梦 DreamScript | 剧本步骤新增「帮我写」：文本模型三段式生成 + 检查清单 | 1–2 天 |
| 8 | **低成本预演**：生视频前先出一张「剧情推演四宫格」看节奏 | LibTV 四宫格、即梦白模预演 | 分镜卡「预演」= 一张 2×2 网格图任务（一次图片费用）；满意再生视频 | 1 天 |
| 9 | **配音 / 配乐参考**：上传音频作为 `[Audio 1]` 驱动（2.5 支持纯音频） | Seedance 音频参考 | 镜头抽屉「配音 / 配乐」上传 → `reference_audio` | 0.5 天（依赖 #1） |
| 10 | **合成导出**：按顺序拼接 + 字幕（对白行）+ BGM | 所有平台 | 浏览器端 ffmpeg.wasm | 2 天 |
| 11 | **Agent 一键出整集**：一句话 → 全链路自动跑完再让人改 | LibTV Skill、即梦小云雀 | 后端编排任务 + 进度页；现有任务链已具备 | 2 天 |

不借鉴：无限画布 / 节点编辑器、3D 导演台（学习成本高，短剧主流程用线性五步 + 表格更直接）。

## 第三轮：镜头连贯、成片预览与风格预设（2026-11-08）

起因是用户反馈：分镜之间太不连贯、没有合并预览、开头的风格选择太少。再看一轮主流平台在这三件事上的做法（来源以教程 / 评测为主，官方口径只有方舟 API 文档，细节可信度参差，见文末）。

### 各平台怎么做连贯

- **即梦「智能多帧」**：上传最多 10 张关键帧生成约 54 秒的连贯长镜头；2.0 版增加视频拼接、锁定某个时段局部修改、「只设尾帧」模式。首尾帧模式是「起始帧 + 结束帧 + 过渡描述」，用来做镜头切换；角色一致性靠「先出角色种子图，再在分镜里开角色参考并提高权重」。短剧工作室把分镜放在时间轨道上组织与预览。
- **可灵**：评测里「首尾帧控制」被用来做一镜到底的运镜；**海螺**同样有首尾帧与长镜头生成，另有声音克隆；**Vidu** 的卖点是多主体角色锁定（同时传多个人物参考图）；**剪映**在「交付整部剧」的榜单里合成（字幕 / 配音 / 成片）分最高、解析与一致性分最低，常作为即梦素材的后道。
- **Seedance / 方舟 API**（我们在用）：`return_last_frame`（默认 false）开启后，可通过「查询任务」接口拿到视频尾帧；Seedance 2.5 的全能参考任务含「参考生视频 / 视频编辑 / 视频延长」三类子任务，2.5 与 2.0 系列接受视频输入。第三方封装（ComfyUI 节点、API 转售商）都把尾帧暴露为 `last_frame_url`，并把它作为下一段的首帧串成长片；方舟官方的「肖像资产指南」说明同账号近 30 天内 Seedance 生成的视频 / 尾帧、Seedream 5.0 文生图属于受信产物，含人脸也可作输入。

### 各平台的风格入口

- 即梦短剧工作室建项目时选题材（都市逆袭 / 古风 / 玄幻…）与竖屏比例，风格选项见于教程的有「写实真人 / 古风二次元 / 3D 动画」；第三方整理称即梦支持电影级写实、二次元（日系 / 国风）、3D 动画、复古胶片、水墨国风，可混合与自定义。
- 攻略普遍把风格分「2D 动漫 / 3D 动画 / 仿真人」三大类，并给每类一组固定提示词（如仿真人用「真实场景，电影质感，写实唯美」）——说明「风格 = 一段稠密提示词」是行业通行做法，而不是一个枚举值。
- 港风、黏土、像素等在搜到的资料里没有确认为任何平台的预设按钮；赛博朋克、水墨画出现在即梦的提示词示例中。

### 落到 Jellyfish 的改动（已完成）

| 问题 | 做法 | 依据 |
| --- | --- | --- |
| 分镜不连贯 | 视频任务带 `return_last_frame`，尾帧转存为 `ShotFrameImage(last)`；下一镜在全能参考里多一张「上一镜结尾画面（承接光线 / 时间 / 场景布置 / 人物站位；本镜按新的景别与运镜重新构图）」；确认单「承接上一镜」开关默认开 → 逐镜串行生成 | 第三方「尾帧接首帧」串片法 + 方舟受信产物规则（尾帧含人脸不被拒）。不直接把尾帧当首帧，是因为短剧相邻镜头多为切镜而非一镜到底，用参考图保留光线 / 站位、让新景别自由构图更合适 |
| 没有合并预览 | 成片页「合成预览」：ffmpeg.wasm 在浏览器里拼成整集 Blob 直接播放，WebVTT 字幕轨同步显示；「下载整集 mp4」复用同一 Blob | 即梦时间轨道预览、剪映合成；全部在浏览器内完成，不占服务端 |
| 风格太少 | 新建作品改为 26 张风格卡（真人实拍 12 / 动画 7 / 艺术 7）+ 「风格补充」自由文本；每张卡是一段介质 / 镜头 / 光线 / 色彩 / 质感的提示词，经 `resolve_style_text` 进所有形象 / 关键帧 / 视频 / 剧本提示词 | 攻略里「风格 = 固定提示词组」的做法；覆盖即梦可见的写实 / 二次元 / 3D / 胶片 / 水墨，并补上短剧常见题材（悬疑黑色、古装、仙侠、年代、轻喜剧）与艺术向（黏土、像素、剪纸、油画） |

未做：多关键帧生成一段长镜头（即梦智能多帧；Seedance 2.5 的视频延长 / 参考视频可做，但一镜 4–30 s 已够短剧用）；创作中途换风格并批量重跑；风格混合。见 `docs/plans/creator-mode.md`。

## 来源

- Higgsfield：[How to Turn a Script into an AI Storyboard and Shot List](https://higgsfield.ai/blog/script-to-ai-storyboard-shot-list)、[Meet Higgsfield Popcorn](https://higgsfield.ai/blog/The-AI-Storyboard-Generator-That-Feels-Like-Directing)、[Best AI video platform for consistent characters](https://higgsfield.ai/blog/best-ai-video-consistent-characters)、[Cinema Studio / Soul ID masterclass](https://www.frankx.ai/guides/higgsfield-ai-video-guide)、[Higgsfield review: camera controls tested](https://dynalord.com/blog/higgsfield-review)、[Popcorn review](https://www.composite.global/news/higgsfield-popcorn-vs-nano-banana)
- LibTV 第二轮：[量子位：LibTV 解锁全自动拍片](https://www.qbitai.com/2026/03/390320.html)、[Liblib 发布 LibTV 深度实测](https://view.inews.qq.com/a/20260319A05XAY00)、[LibTV 无限画布保姆级教程](https://x.com/YangGuangAI/article/2034973086769139721)、[LibTV 节点式工作流落地教程](https://blog.csdn.net/Harrytutu_ZuiYue/article/details/162815335)
- 即梦短剧工作室：[爱范儿：实测即梦短剧工作室](https://www.ifanr.com/1686343)、[即梦短剧工作室保姆级教程](https://www.sohu.com/a/1097007160_121124358)
- Seedance 2.x API：[Seedance 2.0 reference guide: images, video and audio](https://magichour.ai/blog/seedance-20-reference-guide)、[seedance-cli README（参考输入上限与 `[Image 1]` / 时间码语法）](https://github.com/paperfoot/seedance-cli)、[Seedance 2.0 API guide](https://www.datacamp.com/tutorial/seedance-2-0-api-guide)
- LibTV：[AI短剧工业化：从7天到4小时](https://www.sohu.com/a/1054148101_122920010)、[LibTV 详解：无限画布、节点工作流与双入口](https://zhuanlan.zhihu.com/p/2074658392195479098)、[LibTV：从剧本到成片一步搞定](https://zhuanlan.zhihu.com/p/2036940221040824458)、[实测 LibTV](https://zhuanlan.zhihu.com/p/2017944626061919460)、[AI 视频平台推荐与流程指南](https://www.sohu.com/a/1082603714_121899512)
- 即梦短剧工作室：[即梦上新，已装下 AI 创作者的整个工作台](https://www.163.com/dy/article/LB0FJO5D0556CUWO.html)、[即梦上线短剧工作室、DreamScript](https://original.ifeng.com/c/8xo1c3Uuuxn)、[AI 短剧制作：从剧本分镜到视频创作](https://jimeng.jianying.com/tools/ai-short-drama)、[从剧本拆分镜到首尾帧控脸出片](https://blog.csdn.net/weixin_31062533/article/details/168760521)
- LTX Studio：[LTX Studio Review 2026: Storyboard-First Workflow](https://lumalabs.ai/news/ltx-studio-review)、[LTX Studio for Producers](https://ltx.io/studio/solution/producers)、[Script to Video](https://ltx.io/studio/platform/script-to-video)、[End-to-End AI Video Production](https://freeaitool.com/en/image-tools/069-ltx-studio-ai-video-production-complete-guide/)
- 一站式平台盘点：[2026 年 AI 短剧平台推荐](https://zhuanlan.zhihu.com/p/2050989940557850145)、[7 款实用工具综合盘点](https://zhuanlan.zhihu.com/p/2050972345905554994)、[15 个 AI 短剧创作平台](https://ai-bot.cn/ai-skit-generation-tools/)、[AI 短剧制作教程：脚本、画面、配音到成片](https://www.550wai.cn/blog/ai-short-drama-production-guide.html)
- 可灵 / Vidu / 海螺：[四款主流平台选型对比](https://www.sohu.com/a/1087337669_122988336)、[AI 短剧平台大横评](https://bbs.csdn.net/weixin_29056781/article/details/100282332)、[可灵 AI 逐镜制作实战](https://www.seektik.com/ai-short-drama-video-generation/)、[11 款 AI 短剧工具月活对比](https://zhuanlan.zhihu.com/p/2073378435280397521)
- 第三轮（连贯 / 风格）：[做竖屏 AI 短剧用什么软件？2026 主流制作工具横向对比](https://news.qq.com/rain/a/20260624A06V0I00)、[AI 短剧生成工具深度对比：即梦、可灵与 Vidu](https://blog.csdn.net/u014177256/article/details/157644721)、[2026 最好用的 AI 短剧工具排名（按整剧交付能力）](https://sincosphere.cn/best/best-ai-short-drama-tools/)、[即梦 AI 零基础从入门到精通（智能多帧 / 首尾帧 / 多图参考）](https://www.toutiao.com/article/7668591940610327084/)、[即梦 AI 上线「短剧工作室」：三款自研模型](https://zhuanlan.zhihu.com/p/2098703785937868286)、[即梦短剧工作室保姆级教程（题材 / 风格设置）](https://www.sohu.com/a/1097007160_121124358)、[15 个 AI 短剧创作平台（即梦风格列表）](https://ai-bot.cn/ai-skit-generation-tools/)、[AI 短剧工具对决：即梦 vs 可灵（三类风格提示词）](https://post.smzdm.com/p/a032lqdw/)
- 方舟 / Seedance 官方：[Create a video generation task（`return_last_frame`、支持模型、2.5 全能参考子任务）](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/create-video-generation-task-api)、[Seedance 肖像视频便利创作指南（受信模型产物规则）](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh)、[为什么请求被判为敏感内容、如何减少误拒](https://ai.byteplus.com/en/help/article/why-was-my-request-rejected-for-sensitive-or-non-compliant-content-and-how-do-i-reduce-false-rejections)；第三方尾帧串片：[ModelArk Seedance 2.0 ComfyUI 节点（`last_frame_url` 输出）](https://comfy.icu/node/ModelArk-Seedance-2-0)、[awesome-seedance-2.5-api-prompts](https://github.com/Anil-matcha/awesome-seedance-2.5-api-prompts)
