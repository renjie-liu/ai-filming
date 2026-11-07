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

## 来源

- LibTV：[AI短剧工业化：从7天到4小时](https://www.sohu.com/a/1054148101_122920010)、[LibTV 详解：无限画布、节点工作流与双入口](https://zhuanlan.zhihu.com/p/2074658392195479098)、[LibTV：从剧本到成片一步搞定](https://zhuanlan.zhihu.com/p/2036940221040824458)、[实测 LibTV](https://zhuanlan.zhihu.com/p/2017944626061919460)、[AI 视频平台推荐与流程指南](https://www.sohu.com/a/1082603714_121899512)
- 即梦短剧工作室：[即梦上新，已装下 AI 创作者的整个工作台](https://www.163.com/dy/article/LB0FJO5D0556CUWO.html)、[即梦上线短剧工作室、DreamScript](https://original.ifeng.com/c/8xo1c3Uuuxn)、[AI 短剧制作：从剧本分镜到视频创作](https://jimeng.jianying.com/tools/ai-short-drama)、[从剧本拆分镜到首尾帧控脸出片](https://blog.csdn.net/weixin_31062533/article/details/168760521)
- LTX Studio：[LTX Studio Review 2026: Storyboard-First Workflow](https://lumalabs.ai/news/ltx-studio-review)、[LTX Studio for Producers](https://ltx.io/studio/solution/producers)、[Script to Video](https://ltx.io/studio/platform/script-to-video)、[End-to-End AI Video Production](https://freeaitool.com/en/image-tools/069-ltx-studio-ai-video-production-complete-guide/)
- 一站式平台盘点：[2026 年 AI 短剧平台推荐](https://zhuanlan.zhihu.com/p/2050989940557850145)、[7 款实用工具综合盘点](https://zhuanlan.zhihu.com/p/2050972345905554994)、[15 个 AI 短剧创作平台](https://ai-bot.cn/ai-skit-generation-tools/)、[AI 短剧制作教程：脚本、画面、配音到成片](https://www.550wai.cn/blog/ai-short-drama-production-guide.html)
- 可灵 / Vidu / 海螺：[四款主流平台选型对比](https://www.sohu.com/a/1087337669_122988336)、[AI 短剧平台大横评](https://bbs.csdn.net/weixin_29056781/article/details/100282332)、[可灵 AI 逐镜制作实战](https://www.seektik.com/ai-short-drama-video-generation/)、[11 款 AI 短剧工具月活对比](https://zhuanlan.zhihu.com/p/2073378435280397521)
