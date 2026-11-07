/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 某个资源最近一次生成任务的轻量状态（供卡片展示进度 / 失败原因）。
 */
export type CreatorTaskRead = {
    /**
     * 任务 ID
     */
    task_id: string;
    /**
     * pending / running / streaming / succeeded / failed / cancelled
     */
    status: string;
    /**
     * 进度 0-100
     */
    progress: number;
    /**
     * 失败原因（原文，前端负责中文映射）
     */
    error: (string | null);
};

