/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CreatorEntityCreatedRead = {
    type: string;
    id: string;
    /**
     * 同名实体已存在（角色按作品、场景 / 道具 / 服装全局唯一），本次沿用而非新建
     */
    reused: boolean;
};

