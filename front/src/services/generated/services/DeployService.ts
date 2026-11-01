/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_dict_ } from '../models/ApiResponse_dict_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DeployService {
    /**
     * Deploy Status
     * @returns ApiResponse_dict_ Successful Response
     * @throws ApiError
     */
    public static deployStatusApiV1DeployStatusGet({
        probeArk = false,
    }: {
        /**
         * 是否对方舟 API 做只读连通性探测
         */
        probeArk?: boolean,
    }): CancelablePromise<ApiResponse_dict_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/_deploy/status',
            query: {
                'probe_ark': probeArk,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Deploy Selftest Start
     * 按业务任务相同的执行方式分派自检任务，验证「分派 → 执行 → 数据库」链路；返回 token。
     *
     * 使用 GET 便于在浏览器中直接打开（接口受部署保护；默认不调用任何模型供应商）。
     * @returns ApiResponse_dict_ Successful Response
     * @throws ApiError
     */
    public static deploySelftestStartApiV1DeploySelftestGet({
        llm = false,
    }: {
        /**
         * 是否在任务中调用默认文本模型（一句极短请求，成本极低）
         */
        llm?: boolean,
    }): CancelablePromise<ApiResponse_dict_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/_deploy/selftest',
            query: {
                'llm': llm,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Deploy Selftest Result
     * 查询自检结果：`done=false` 表示 worker 尚未执行（或队列未投递）。
     * @returns ApiResponse_dict_ Successful Response
     * @throws ApiError
     */
    public static deploySelftestResultApiV1DeploySelftestTokenGet({
        token,
    }: {
        token: string,
    }): CancelablePromise<ApiResponse_dict_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/_deploy/selftest/{token}',
            path: {
                'token': token,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
