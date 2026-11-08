/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProjectStyle } from './ProjectStyle';
import type { ProjectVisualStyle } from './ProjectVisualStyle';
export type ProjectRead = {
    /**
     * 项目名称
     */
    name: string;
    /**
     * 项目简介
     */
    description?: string;
    /**
     * 题材/风格
     */
    style: ProjectStyle;
    /**
     * 画面表现形式
     */
    visual_style?: ProjectVisualStyle;
    /**
     * 随机种子
     */
    seed?: number;
    /**
     * 是否统一风格
     */
    unify_style?: boolean;
    /**
     * 进度百分比（0-100）
     */
    progress?: number;
    /**
     * 项目级默认视频比例；分镜未覆盖时生效
     */
    default_video_ratio?: (string | null);
    /**
     * 画面风格预设 key（见 /projects/style-options 的 presets）；给出时 visual_style / style 以预设为准
     */
    style_preset?: (string | null);
    /**
     * 自定义风格补充描述，拼在预设提示词之后进入所有提示词
     */
    style_prompt?: (string | null);
    /**
     * 聚合统计（JSON）
     */
    stats?: Record<string, any>;
    id: string;
    /**
     * 展示用风格名：预设名（如「电影胶片」）或旧题材值（如「真人都市」）
     */
    readonly style_label: string;
};

