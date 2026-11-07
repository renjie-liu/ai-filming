/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一张可「采用」的图片：历史生成结果或上传图；is_current 表示当前正在用的那张。
 */
export type CreatorImageCandidateRead = {
    file_id: string;
    url: string;
    /**
     * 来自哪次生成任务；上传图为空
     */
    task_id: (string | null);
    created_at: (string | null);
    is_current: boolean;
};

