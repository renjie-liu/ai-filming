/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreatorTaskRead } from './CreatorTaskRead';
/**
 * 角色的一个视角形象（侧面 / 背面 …），用于多视图参考。
 */
export type CreatorEntityViewRead = {
    /**
     * LEFT / RIGHT / BACK / THREE_QUARTER …
     */
    view_angle: string;
    image_id: number;
    file_id: (string | null);
    url: string;
    task: (CreatorTaskRead | null);
};

