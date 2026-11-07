/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 创作页手动新增角色 / 场景 / 道具 / 服装，并可直接挂到若干镜头。
 */
export type CreatorEntityCreate = {
    type: 'character' | 'scene' | 'prop' | 'costume';
    name: string;
    /**
     * 设定描述；会作为形象图提示词的素材
     */
    description?: string;
    shot_ids?: Array<string>;
};

