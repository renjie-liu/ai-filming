/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AuthStatusRead_ } from '../models/ApiResponse_AuthStatusRead_';
import type { ApiResponse_list_UserRead__ } from '../models/ApiResponse_list_UserRead__';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_RegistrationSettingsRead_ } from '../models/ApiResponse_RegistrationSettingsRead_';
import type { ApiResponse_UserRead_ } from '../models/ApiResponse_UserRead_';
import type { LoginRequest } from '../models/LoginRequest';
import type { PasswordChangeRequest } from '../models/PasswordChangeRequest';
import type { RegisterRequest } from '../models/RegisterRequest';
import type { RegistrationSettingsUpdate } from '../models/RegistrationSettingsUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AuthService {
    /**
     * 登录页公开状态：是否有用户、能否注册
     * @returns ApiResponse_AuthStatusRead_ Successful Response
     * @throws ApiError
     */
    public static authStatusApiV1AuthStatusGet(): CancelablePromise<ApiResponse_AuthStatusRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/status',
        });
    }
    /**
     * 注册并登录
     * @returns ApiResponse_UserRead_ Successful Response
     * @throws ApiError
     */
    public static registerApiV1AuthRegisterPost({
        requestBody,
    }: {
        requestBody: RegisterRequest,
    }): CancelablePromise<ApiResponse_UserRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/register',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 邮箱密码登录
     * @returns ApiResponse_UserRead_ Successful Response
     * @throws ApiError
     */
    public static loginApiV1AuthLoginPost({
        requestBody,
    }: {
        requestBody: LoginRequest,
    }): CancelablePromise<ApiResponse_UserRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 退出登录（清除会话 cookie）
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static logoutApiV1AuthLogoutPost(): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/logout',
        });
    }
    /**
     * 当前登录用户
     * @returns ApiResponse_UserRead_ Successful Response
     * @throws ApiError
     */
    public static meApiV1AuthMeGet(): CancelablePromise<ApiResponse_UserRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/me',
        });
    }
    /**
     * 修改当前用户的密码
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static changePasswordApiV1AuthPasswordPost({
        requestBody,
    }: {
        requestBody: PasswordChangeRequest,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/password',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 注册设置（管理员）
     * @returns ApiResponse_RegistrationSettingsRead_ Successful Response
     * @throws ApiError
     */
    public static getRegistrationSettingsApiV1AuthSettingsGet(): CancelablePromise<ApiResponse_RegistrationSettingsRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/settings',
        });
    }
    /**
     * 修改注册设置（管理员）
     * @returns ApiResponse_RegistrationSettingsRead_ Successful Response
     * @throws ApiError
     */
    public static updateRegistrationSettingsApiV1AuthSettingsPut({
        requestBody,
    }: {
        requestBody: RegistrationSettingsUpdate,
    }): CancelablePromise<ApiResponse_RegistrationSettingsRead_> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/auth/settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 用户列表（管理员）
     * @returns ApiResponse_list_UserRead__ Successful Response
     * @throws ApiError
     */
    public static listUsersApiV1AuthUsersGet(): CancelablePromise<ApiResponse_list_UserRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/users',
        });
    }
}
