"""镜头细节（ShotDetail）的默认值与补齐。

为什么存在：
- 视频生成、时长读取、视频准备度都依赖 ShotDetail（时长 / 景别 / 机位 / 运镜）；
- AI 拆分镜会同时写入 Shot 与 ShotDetail，但手动「新建分镜」此前只写 Shot，
  且没有任何页面能再补建 ShotDetail，导致手动镜头永远无法生成视频（后端返回 ShotDetail not found）；
- 这里统一提供默认细节，供新建镜头、AI 拆分写库与存量数据补齐共用，保证两条创建路径结果一致。

本模块只依赖模型层，避免与其它 service 模块循环导入。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import CameraAngle, CameraMovement, CameraShotType, Shot, ShotDetail, VFXType

# 默认镜头时长（秒）：与 AI 拆分镜写库一致，也处于 Seedance 各版本支持的时长区间内。
DEFAULT_SHOT_DURATION_SECONDS = 4


def build_default_shot_detail(shot_id: str) -> ShotDetail:
    """构造镜头的默认细节：中景、平视、固定机位、无特效、默认时长。

    参数：
    - shot_id：镜头 ID（ShotDetail 与 Shot 共用主键）。
    返回：尚未加入会话的 ShotDetail 实例。
    """
    return ShotDetail(
        id=shot_id,
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        duration=DEFAULT_SHOT_DURATION_SECONDS,
    )


async def backfill_missing_shot_details(db: AsyncSession) -> int:
    """为缺少 ShotDetail 的存量镜头补齐默认细节（幂等）。

    返回：本次补齐的镜头数量。调用方负责提交事务。
    """
    rows = await db.execute(
        select(Shot.id).outerjoin(ShotDetail, ShotDetail.id == Shot.id).where(ShotDetail.id.is_(None))
    )
    shot_ids = [row[0] for row in rows.all()]
    for shot_id in shot_ids:
        db.add(build_default_shot_detail(shot_id))
    if shot_ids:
        await db.flush()
    return len(shot_ids)
