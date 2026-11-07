/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 自动确认结果汇总。
 */
export type AutoConfirmResultRead = {
    shot_count?: number;
    /**
     * 已关联的资产候选数
     */
    linked_candidates?: number;
    /**
     * 已接受的对白候选数
     */
    accepted_dialogues?: number;
    /**
     * 新建的实体数
     */
    created_entities?: number;
    /**
     * 因没有提取结果而标记为无需提取的镜头数
     */
    skipped_shots?: number;
    /**
     * 处理后处于 ready 的镜头数
     */
    ready_shots?: number;
};

