/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一个可直接套用的画面风格预设（新建作品时的风格卡片）。
 */
export type StylePresetRead = {
    /**
     * 预设 key，写入 Project.style_preset
     */
    key: string;
    /**
     * 卡片标题
     */
    label: string;
    /**
     * 分组：真人实拍 / 动画 / 艺术
     */
    group: string;
    /**
     * 预设对应的画面表现形式（现实 / 动漫）
     */
    visual_style: string;
    /**
     * 预设对应的题材粗分桶
     */
    style: string;
    /**
     * 进入提示词的风格描述
     */
    prompt: string;
    /**
     * 一句话说明
     */
    blurb?: string;
    /**
     * 卡片小标签
     */
    tags?: Array<string>;
};

