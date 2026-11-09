/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type RegistrationSettingsUpdate = {
    /**
     * 允许 / 关闭注册
     */
    enabled?: (boolean | null);
    /**
     * 设置邀请码；传空串表示清除（开放注册）
     */
    invite_code?: (string | null);
    /**
     * 为真时随机生成一个新邀请码（忽略 invite_code）
     */
    regenerate_invite_code?: boolean;
};

