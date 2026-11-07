/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 按类型整体替换镜头「画面里会用到」的实体；为 None 的类型保持不变。
 */
export type ShotEntityLinksWrite = {
    /**
     * 角色 ID 列表（按画面内顺序）
     */
    character_ids?: (Array<string> | null);
    scene_ids?: (Array<string> | null);
    prop_ids?: (Array<string> | null);
    costume_ids?: (Array<string> | null);
};

