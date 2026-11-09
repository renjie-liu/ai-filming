/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type RegisterRequest = {
    /**
     * 邮箱
     */
    email: string;
    /**
     * 密码（至少 8 位）
     */
    password: string;
    /**
     * 显示名，可空
     */
    display_name?: string;
    /**
     * 邀请码；注册模式为 invite 时必填
     */
    invite_code?: (string | null);
};

