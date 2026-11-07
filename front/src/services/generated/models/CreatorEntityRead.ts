/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreatorEntityViewRead } from './CreatorEntityViewRead';
import type { CreatorImageCandidateRead } from './CreatorImageCandidateRead';
import type { CreatorTaskRead } from './CreatorTaskRead';
/**
 * 创作页角色 / 场景 / 道具 / 服装卡。
 */
export type CreatorEntityRead = {
    type: 'character' | 'scene' | 'prop' | 'costume';
    id: string;
    name: string;
    description: string;
    /**
     * 形象 / 参考图地址；无图为空
     */
    thumbnail: string;
    /**
     * 形象图行 ID（创建图片任务时使用）
     */
    image_id: (number | null);
    /**
     * 形象图文件 ID（作为关键帧 / 视频的参考图）
     */
    image_file_id: (string | null);
    /**
     * 最近一次形象图任务
     */
    image_task: (CreatorTaskRead | null);
    /**
     * 本章节内出现的镜头数；0 表示本集尚未用到（可能沿用自其它集）
     */
    shot_count: number;
    /**
     * 本章节内出现的镜头 ID
     */
    shot_ids: Array<string>;
    /**
     * 形象 / 参考图候选与历史（当前在前，最多 8 张）
     */
    image_candidates: Array<CreatorImageCandidateRead>;
    /**
     * 角色的其它视角形象（侧面 / 背面）
     */
    views: Array<CreatorEntityViewRead>;
};

