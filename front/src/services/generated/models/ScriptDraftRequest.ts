/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一句话起草剧本请求。
 */
export type ScriptDraftRequest = {
    /**
     * 作品 ID（题材 / 画面风格从这里取）
     */
    project_id: string;
    /**
     * 章节 ID（可选；给出时按该集的集数写，任务关联到章节）
     */
    chapter_id?: (string | null);
    /**
     * 一句话创意 / 故事想法
     */
    idea: string;
    /**
     * 目标成片时长（秒），决定剧本篇幅
     */
    target_seconds?: number;
    /**
     * 前情提要或补充要求（可选，例如上一集结尾、必须出现的角色）
     */
    context?: (string | null);
};

