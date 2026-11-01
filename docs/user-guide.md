# Using Jellyfish: from script to video

The same guide is built into the app: open **Guide** (使用指南) in the left menu. The
project list also shows a **Quick start** card until you dismiss it. App buttons are
in Chinese, so this guide quotes each one in 「」 with its English meaning.

AI models need no setup. The deployment connects Seedance automatically, and the
banner at the top of the Guide and Model Management pages shows the default text,
image and video models.

## 1. Create a project
- On the project list, click 「新建项目」 (New project).
- Enter 「项目名称」 (Project name) and choose 「视觉风格」 (Visual style) and 「视频风格」 (Video style).
- Also set 「默认视频比例」 (Default aspect ratio), e.g. 9:16. Video generation needs it.
- Click 「创建并进入」 (Create and open).

## 2. Paste your script
- In the project workbench, open the 「章节」 (Chapters) tab and click 「创建第一章」 / 「新建章节」 (New chapter).
- Enter 「章节标题」 (Chapter title) and paste the script into 「章节内容（可粘贴剧本）」 (Chapter content), then click 「创建」 (Create).
- In the 「章节创建成功」 (Chapter created) dialog, click 「立即提取分镜」 (Extract shots now).

## 3. Split into shots (AI)
- Click 「提取分镜」 (Extract shots) on the chapter row, or 「一键提取分镜」 on the shots page.
- It takes about 1–2 minutes. Progress shows in 「任务中心」 (Task center), the floating button at the bottom left.

## 4. Confirm each shot (shot editor = preparation)
- On a shot, click 「编辑」 (Edit), open 「2 提取确认」 (Extraction review) and click 「提取并刷新候选」 (Extract candidates).
- For each asset candidate, click 「关联」 (Link) / 「新建」 (Create) / 「忽略」 (Ignore). For dialogue, click 「全部接受」 (Accept all). For a shot with nothing to extract, click 「无需提取」 (No extraction needed).
- 「准备完成」 (Ready) means the shot is ready. Use 「继续处理下一个待处理镜头」 (Next pending shot) to move on.

## 5. Make keyframes (studio = generation)
- Click 「进入工作室」 (Open studio). In 「分镜生成面板」 (Generation panel), open 「关键帧与参考图」 (Keyframes & references).
- On 「首帧图片」 (First frame), click 「生成」 (Generate). Optionally click 「AI生成」 (AI draft) to write the prompt, then click 「生成」 (Generate). Seedream takes about 10–30 seconds.

## 6. Generate the video
- Open the 「视频生成」 (Video) tab and check that 「视频准备度」 (Video readiness) shows 「可生成」 (Ready).
- Click 「生成视频」 (Generate video), then 「生成」 (Generate). Seedance takes about 1–3 minutes, and clips appear under 「已生成视频」 (Generated videos).
- For several shots: select them on the left and click 「批量生成」 (Batch generate).
- When you're done, click 「进入后期剪辑」 (Open editor) in the project workbench to cut the clips together.

## Tips
- Images and videos use Seedance credits, and video is the expensive part. Try one shot before batch-generating.
- On Vercel's Hobby plan, each generation must finish within 5 minutes. A job that times out stays shown as running; generate it again.
