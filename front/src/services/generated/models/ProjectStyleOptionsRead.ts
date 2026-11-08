/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StyleOption } from './StyleOption';
import type { StylePresetRead } from './StylePresetRead';
/**
 * 项目风格候选项。
 */
export type ProjectStyleOptionsRead = {
    /**
     * 预设分组顺序
     */
    preset_groups?: Array<string>;
    /**
     * 画面风格预设目录
     */
    presets?: Array<StylePresetRead>;
    /**
     * 新建作品默认选中的预设 key
     */
    default_preset?: (string | null);
    /**
     * 视觉风格可选项
     */
    visual_styles?: Array<StyleOption>;
    /**
     * 按视觉风格分组的视频风格选项
     */
    styles_by_visual_style?: Record<string, Array<StyleOption>>;
    /**
     * 各视觉风格默认视频风格
     */
    default_style_by_visual_style?: Record<string, string>;
};

