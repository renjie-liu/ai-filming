/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreatorChapterRead } from './CreatorChapterRead';
import type { CreatorEntityRead } from './CreatorEntityRead';
import type { CreatorProjectRead } from './CreatorProjectRead';
import type { CreatorShotRead } from './CreatorShotRead';
import type { CreatorSummaryRead } from './CreatorSummaryRead';
import type { CreatorTaskRead } from './CreatorTaskRead';
/**
 * 创作页聚合读模型。
 */
export type CreatorBoardRead = {
    project: CreatorProjectRead;
    chapter: CreatorChapterRead;
    shots: Array<CreatorShotRead>;
    entities: Array<CreatorEntityRead>;
    summary: CreatorSummaryRead;
    /**
     * 最近一次拆分镜任务
     */
    divide_task: (CreatorTaskRead | null);
    /**
     * 最近一次角色场景提取任务
     */
    extract_task: (CreatorTaskRead | null);
};

