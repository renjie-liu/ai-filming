/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 对外的用户信息（不含密码哈希）。
 */
export type UserRead = {
    id: string;
    email: string;
    display_name?: string;
    is_admin?: boolean;
    created_at?: (string | null);
    last_login_at?: (string | null);
};

