/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 登录页需要的公开状态：有没有用户、现在能否注册、注册要不要邀请码。
 */
export type AuthStatusRead = {
    /**
     * 是否已有任何用户；没有时第一个注册者成为管理员
     */
    has_users: boolean;
    /**
     * first_admin=等待首个管理员注册；open=开放注册；invite=需邀请码；closed=关闭注册
     */
    registration: 'first_admin' | 'open' | 'invite' | 'closed';
};

