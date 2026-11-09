/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 管理员可见的注册设置。
 */
export type RegistrationSettingsRead = {
    /**
     * 是否允许新用户注册
     */
    enabled: boolean;
    /**
     * 邀请码；为空表示开放注册（在 enabled 为真时）
     */
    invite_code?: (string | null);
    /**
     * 当前用户数
     */
    user_count?: number;
};

