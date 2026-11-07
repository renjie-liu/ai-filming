/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 作品列表卡片。
 */
export type ProjectOverviewRead = {
    id: string;
    name: string;
    description: string;
    style: string;
    visual_style: string;
    default_video_ratio: (string | null);
    chapter_count: number;
    shot_count: number;
    keyframe_count: number;
    video_count: number;
    /**
     * 封面：第一张关键帧
     */
    cover_url: (string | null);
    /**
     * 最近编辑的章节，进入创作页时默认打开
     */
    latest_chapter_id: (string | null);
    updated_at: (string | null);
};

