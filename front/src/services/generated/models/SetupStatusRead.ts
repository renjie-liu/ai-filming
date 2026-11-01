/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SetupModelRead } from './SetupModelRead';
import type { SetupProviderRead } from './SetupProviderRead';
/**
 * 开箱即用状态：前端据此决定是否提示「无需配置」或引导去模型管理。
 */
export type SetupStatusRead = {
    /**
     * 文本 / 图片 / 视频默认模型均已就绪且供应商已有 API Key
     */
    ready: boolean;
    /**
     * 部署自动配置的供应商（如有）
     */
    managed_provider?: (SetupProviderRead | null);
    /**
     * 默认文本模型
     */
    text_model?: (SetupModelRead | null);
    /**
     * 默认图片模型
     */
    image_model?: (SetupModelRead | null);
    /**
     * 默认视频模型
     */
    video_model?: (SetupModelRead | null);
    /**
     * 缺少可用默认模型的类别：text / image / video
     */
    missing?: Array<string>;
};

