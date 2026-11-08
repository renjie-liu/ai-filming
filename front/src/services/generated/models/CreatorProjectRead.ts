/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CreatorProjectRead = {
    id: string;
    name: string;
    style: string;
    visual_style: string;
    /**
     * 画面风格预设 key；老作品为空
     */
    style_preset: (string | null);
    /**
     * 展示用风格名：预设名或旧题材值
     */
    style_label: string;
    default_video_ratio: (string | null);
};

