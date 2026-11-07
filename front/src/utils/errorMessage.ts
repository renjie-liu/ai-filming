/**
 * 错误提示中文化工具。
 *
 * 为什么存在：后端（以及 Seedance / 方舟等供应商）返回的错误多为英文，
 * 部分页面会把它们原样弹出；界面统一为中文后，这里把常见错误映射为中文说明，
 * 无法识别的英文错误显示调用方给出的中文兜底文案（原文输出到控制台便于排查）。
 */

const CJK_RE = /[一-鿿]/

const CATEGORY_LABELS: Record<string, string> = { text: '文本', image: '图片', video: '视频' }

/** [匹配规则, 中文文案]；按顺序匹配，命中第一条即返回。 */
const RULES: Array<[RegExp, string | ((m: RegExpMatchArray) => string)]> = [
  // ---- 模型 / 供应商配置 ----
  [/No default model configured for category=(\w+)/i, (m) => `尚未设置默认${CATEGORY_LABELS[m[1]] ?? ''}模型，请在「模型管理 → 设置」中选择`],
  [/No default video model configured/i, '尚未设置默认视频模型，请在「模型管理 → 设置」中选择'],
  [/No image model configured/i, '尚未设置默认图片模型，请在「模型管理 → 设置」中选择'],
  [/No text model configured/i, '该供应商下没有文本模型，请在「模型管理」中添加'],
  [/Provider api_key is empty/i, '供应商缺少 API Key，请检查部署环境变量 SEEDDANCE_API_KEY'],
  [/Provider is disabled/i, '该模型供应商已停用，请在「模型管理」中启用'],
  [/Configured (default )?(video )?model (not found|is not)/i, '默认模型配置无效，请在「模型管理 → 设置」中重新选择'],
  [/Provider not found/i, '模型供应商不存在，请在「模型管理」中检查配置'],
  [/does not support category=(\w+)/i, (m) => `该供应商不支持${CATEGORY_LABELS[m[1]] ?? ''}模型`],
  [/Install (httpx|langchain-openai)/i, '服务端缺少运行依赖，请联系管理员'],
  // ---- 供应商（Seedance / 方舟）常见错误码 ----
  [/ModelNotOpen|InvalidEndpointOrModel|not activated/i, '模型未在 Seedance 账户中开通，请在 BytePlus 控制台开通或在「模型管理」中更换模型'],
  [/InsufficientBalance|AccountOverdue|Insufficient(Quota|Funds)|quota/i, 'Seedance 账户余额或额度不足，请充值后重试'],
  [/RateLimit|TooManyRequests|429/i, '请求过于频繁，请稍后重试'],
  // 方舟内容审核：区分「生成结果被拦截（含版权）」与「输入的提示词 / 图片被拦截」，给出可操作的修改方向。
  [/OutputVideoSensitiveContentDetected[\s\S]*copyright|copyright/i, '生成的视频疑似涉及版权内容（如知名角色、品牌、影视作品或音乐），未通过平台审核。请把提示词改成原创的人物与场景描述后重试'],
  [/Output(Video|Audio|Image)SensitiveContentDetected/i, '生成的视频未通过平台内容审核，请调整提示词后重试'],
  [/InputImageSensitiveContentDetected\.PrivacyInformation|may contain real person/i, '视频平台不接受含真人形象的参考图（真人实拍风格常见）。可以改用「仅文字描述」生成，或把作品画面改为动漫'],
  [/InputImageSensitiveContentDetected/i, '参考图片未通过内容安全审核，请更换图片后重试'],
  [/Input(Text)?SensitiveContentDetected/i, '提示词未通过内容安全审核，请修改后重试'],
  [/Sensitive|\brisk\b|ContentPolicy|moderation|PolicyViolation/i, '提示词或图片未通过内容安全审核，请修改后重试'],
  [/AuthenticationError|Unauthorized|401|api key doesn't exist/i, 'Seedance API Key 无效，请检查部署环境变量 SEEDDANCE_API_KEY'],
  [/parameter ratio .*not valid|ratio is required/i, '视频比例不可用，请检查项目默认比例或镜头比例'],
  [/parameter duration .*not valid|duration .*must be/i, '视频时长不在模型支持范围内，请调整镜头时长'],
  [/timed? ?out|Timeout/i, '生成超时，请稍后重试'],
  // ---- 业务校验 ----
  [/Shot duration is not configured/i, '镜头未设置时长，请先在分镜中设置时长'],
  [/ShotDetail not found/i, '镜头缺少详情（时长、景别等），请刷新页面后重试'],
  [/Required frame image is missing: (\w+)/i, '缺少所需的关键帧图片，请先在「关键帧与参考图」中生成'],
  [/requires exactly (\d+) images?, got (\d+)/i, (m) => `参考图数量不符：需要 ${m[1]} 张，当前 ${m[2]} 张`],
  [/prompt is required/i, '提示词不能为空'],
  [/Chapter already has shots/i, '该章节已有分镜，请先清空后再重新提取'],
  [/does not belong to/i, '数据归属不一致，请刷新页面后重试'],
  [/Invalid image file_id|File is not an image|Empty file content|Failed to download file/i, '参考图片不可用，请重新生成或上传'],
  [/Failed to (divide|extract|merge|analyze|check|optimize|simplify)/i, 'AI 处理失败，请稍后重试'],
  [/is required/i, '缺少必填信息，请补充后重试'],
  [/already exists/i, '数据已存在'],
  [/not found/i, '数据不存在或已被删除，请刷新页面'],
  // ---- 数据库（Neon Postgres）----
  [/exceeded the quota|Database quota exceeded|数据库.*额度/i, '数据库（Neon）已超出免费额度，暂时无法读写。请在 Neon 控制台升级套餐或等待额度重置后再试'],
  [/Database unavailable|connection to server at .* failed/i, '数据库暂时无法连接，请稍后重试'],
  // ---- 对象存储（Vercel Blob）----
  [/BlobStoreSuspended|limits-exceeded|usage ?quota|store has been suspended/i, '素材存储（Vercel Blob）已超出免费额度被暂停，图片和视频暂时无法保存。请在 Vercel 控制台升级套餐或等待额度重置，也可以改用 S3 兼容存储'],
  [/BlobServiceRateLimited/i, '存储服务限流，请稍后重试'],
  [/BlobCredentialsError|BlobAccessError|BlobStoreNotFound|Blob storage unavailable/i, '素材存储暂不可用，请检查 Vercel Blob 配置（BLOB_READ_WRITE_TOKEN）'],
  [/No reference images available/i, '这个镜头还没有可用的参考图：先给角色生成形象或生成关键帧，或者改用「仅文字」'],
  [/reference_mode=reference requires 1-9 images/i, '形象参考最多 9 张、至少 1 张，请调整勾选'],
  [/url does not match the prepared upload path|invalid upload pathname|invalid storage key/i, '上传校验失败，请重新上传'],
  [/direct upload is unavailable/i, '当前存储不支持浏览器直传，视频 / 音频需在 4 MB 以内'],
  // ---- 创作页：三视图 / 四宫格 / 音频参考 ----
  [/Character has no front portrait/i, '角色还没有正面形象，先生成或上传一张，再派生侧面 / 背面'],
  [/unsupported view/i, '不支持的视角'],
  [/file is not audio|File is not audio/i, '请选择音频文件（mp3 / wav / m4a / aac）'],
  [/Audio reference needs a public URL/i, '音频需要可公网访问的地址，请重新上传一次'],
  [/Invalid audio file_id/i, '音频文件不可用，请重新上传'],
  [/file is not a video/i, '请选择视频文件（mp4 / mov / webm）'],
  [/shot_ids must contain every shot/i, '镜头列表已变化，请刷新页面后再调整顺序'],
  // ---- 合成导出（浏览器内）----
  [/Failed to fetch|NetworkError|fetchFile|403/i, '片段下载失败：素材存储暂不可用或不允许跨域读取，请稍后重试'],
  [/WebAssembly|wasm|SharedArrayBuffer/i, '当前浏览器不支持浏览器内合成，请换用最新版 Chrome / Edge / Safari'],
  // ---- 上传 ----
  [/Request Entity Too Large|Payload Too Large|FUNCTION_PAYLOAD_TOO_LARGE|\b413\b/i, '图片太大，请换一张 4 MB 以内的图片'],
  [/Unsupported file type|unsupported (image|media) type/i, '不支持的图片格式，请使用 JPG / PNG / WebP'],
  // ---- HTTP 状态文本 ----
  [/^Bad Request$/i, '请求参数有误'],
  [/^Not Found$/i, '数据不存在或已被删除'],
  [/^Unprocessable Entity$/i, '提交的数据格式不正确'],
  [/^Service Unavailable$/i, '服务暂不可用，请稍后重试'],
  [/^Internal Server Error$/i, '服务器内部错误，请稍后重试'],
  [/^(Failed to fetch|Network ?Error|Load failed)$/i, '网络异常，请检查网络后重试'],
]

/**
 * 从异常对象中提取后端 / 网络错误原文。
 *
 * 兼容：统一响应 `{ code, message }`（body.message）、FastAPI `{ detail }`、生成客户端 ApiError、字符串。
 */
export function extractErrorText(error: unknown): string {
  if (!error) return ''
  if (typeof error === 'string') return error.trim()
  if (typeof error === 'object') {
    const e = error as { body?: { detail?: unknown; message?: unknown }; detail?: unknown; message?: unknown }
    for (const candidate of [e.body?.detail, e.body?.message, e.detail, e.message]) {
      if (typeof candidate === 'string' && candidate.trim()) return candidate.trim()
    }
  }
  return ''
}

/**
 * 把错误原文转换为中文提示。
 *
 * @param raw 错误原文（可能为英文）
 * @param fallback 无法识别时显示的中文兜底文案
 * @returns 中文提示：原文已含中文则原样返回；命中规则返回对应中文；否则返回 fallback
 */
export function localizeErrorMessage(raw: string | null | undefined, fallback: string): string {
  const text = (raw ?? '').trim()
  if (!text) return fallback
  if (CJK_RE.test(text)) return text
  for (const [pattern, replacement] of RULES) {
    const match = text.match(pattern)
    if (match) return typeof replacement === 'function' ? replacement(match) : replacement
  }
  // eslint-disable-next-line no-console
  console.warn('[error]', text)
  return fallback
}

/** 便捷组合：从异常中提取原文并转换为中文提示。 */
export function toChineseErrorMessage(error: unknown, fallback: string): string {
  return localizeErrorMessage(extractErrorText(error), fallback)
}
