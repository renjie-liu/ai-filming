/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreatorDialogueLineRead } from './CreatorDialogueLineRead';
import type { CreatorImageCandidateRead } from './CreatorImageCandidateRead';
import type { CreatorTaskRead } from './CreatorTaskRead';
/**
 * 创作页分镜卡所需的镜头信息。
 */
export type CreatorShotRead = {
    id: string;
    index: number;
    title: string;
    script_excerpt: string;
    /**
     * shot.status：pending / ready（信息确认状态）
     */
    status: string;
    /**
     * 时长（秒）
     */
    duration: number;
    /**
     * 景别 code（ECU / CU / MCU / MS / MLS / LS / ELS）
     */
    camera_shot: string;
    /**
     * 机位角度 code（EYE_LEVEL / HIGH_ANGLE / LOW_ANGLE / BIRD_EYE / DUTCH / OVER_SHOULDER）
     */
    angle: string;
    /**
     * 运镜 code（STATIC / PAN / DOLLY_IN …）
     */
    movement: string;
    /**
     * 动作节拍（按时长平均分配时间码写进视频提示词）
     */
    action_beats: Array<string>;
    /**
     * 画面描述（首帧提示词；AI 生成后可编辑）
     */
    description: string;
    dialogue: Array<CreatorDialogueLineRead>;
    character_ids: Array<string>;
    scene_ids: Array<string>;
    prop_ids: Array<string>;
    /**
     * 首帧图片文件 ID
     */
    keyframe_file_id: (string | null);
    /**
     * 首帧图片地址
     */
    keyframe_url: (string | null);
    /**
     * 最近一次首帧提示词任务
     */
    keyframe_prompt_task: (CreatorTaskRead | null);
    /**
     * 最近一次首帧图片任务
     */
    keyframe_image_task: (CreatorTaskRead | null);
    /**
     * 关键帧候选 / 历史（当前在前，最多 8 张）
     */
    keyframe_candidates: Array<CreatorImageCandidateRead>;
    /**
     * 预演四宫格图片地址
     */
    preview_grid_url: (string | null);
    /**
     * 最近一次预演四宫格任务
     */
    preview_grid_task: (CreatorTaskRead | null);
    /**
     * 配音 / 配乐参考文件 ID
     */
    audio_file_id: (string | null);
    /**
     * 配音 / 配乐参考地址
     */
    audio_url: (string | null);
    /**
     * 生成视频文件 ID
     */
    video_file_id: (string | null);
    /**
     * 生成视频地址
     */
    video_url: (string | null);
    /**
     * 最近一次视频任务
     */
    video_task: (CreatorTaskRead | null);
};

