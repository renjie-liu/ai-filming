/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_SetupStatusRead_ } from '../models/ApiResponse_SetupStatusRead_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SystemService {
    /**
     * 开箱即用配置状态
     * 返回默认模型是否就绪、以及由部署自动配置的供应商（不含密钥）。
     * @returns ApiResponse_SetupStatusRead_ Successful Response
     * @throws ApiError
     */
    public static setupStatusApiV1SystemSetupStatusGet(): CancelablePromise<ApiResponse_SetupStatusRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/system/setup-status',
        });
    }
}
