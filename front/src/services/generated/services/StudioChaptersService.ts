/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AutoConfirmResultRead_ } from '../models/ApiResponse_AutoConfirmResultRead_';
import type { ApiResponse_ChapterRead_ } from '../models/ApiResponse_ChapterRead_';
import type { ApiResponse_CreatorBoardRead_ } from '../models/ApiResponse_CreatorBoardRead_';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ChapterRead__ } from '../models/ApiResponse_PaginatedData_ChapterRead__';
import type { ChapterCreate } from '../models/ChapterCreate';
import type { ChapterUpdate } from '../models/ChapterUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioChaptersService {
    /**
     * 章节列表（分页）
     * @returns ApiResponse_PaginatedData_ChapterRead__ Successful Response
     * @throws ApiError
     */
    public static listChaptersApiV1StudioChaptersGet({
        projectId,
        q,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
    }: {
        /**
         * 按项目过滤
         */
        projectId?: (string | null),
        /**
         * 关键字，过滤 title/summary
         */
        q?: (string | null),
        /**
         * 排序字段
         */
        order?: (string | null),
        /**
         * 是否倒序
         */
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_ChapterRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/chapters',
            query: {
                'project_id': projectId,
                'q': q,
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建章节
     * @returns ApiResponse_ChapterRead_ Successful Response
     * @throws ApiError
     */
    public static createChapterApiV1StudioChaptersPost({
        requestBody,
    }: {
        requestBody: ChapterCreate,
    }): CancelablePromise<ApiResponse_ChapterRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/chapters',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取章节
     * @returns ApiResponse_ChapterRead_ Successful Response
     * @throws ApiError
     */
    public static getChapterApiV1StudioChaptersChapterIdGet({
        chapterId,
    }: {
        chapterId: string,
    }): CancelablePromise<ApiResponse_ChapterRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/chapters/{chapter_id}',
            path: {
                'chapter_id': chapterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新章节
     * @returns ApiResponse_ChapterRead_ Successful Response
     * @throws ApiError
     */
    public static updateChapterApiV1StudioChaptersChapterIdPatch({
        chapterId,
        requestBody,
    }: {
        chapterId: string,
        requestBody: ChapterUpdate,
    }): CancelablePromise<ApiResponse_ChapterRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/chapters/{chapter_id}',
            path: {
                'chapter_id': chapterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除章节
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteChapterApiV1StudioChaptersChapterIdDelete({
        chapterId,
    }: {
        chapterId: string,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/chapters/{chapter_id}',
            path: {
                'chapter_id': chapterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：自动确认章节内全部提取候选（建档、关联、接受对白）
     * 把「提取确认」自动化；状态语义不变，处理后镜头按原规则进入 ready。
     * @returns ApiResponse_AutoConfirmResultRead_ Successful Response
     * @throws ApiError
     */
    public static autoConfirmChapterApiApiV1StudioChaptersChapterIdAutoConfirmPost({
        chapterId,
    }: {
        chapterId: string,
    }): CancelablePromise<ApiResponse_AutoConfirmResultRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/chapters/{chapter_id}/auto-confirm',
            path: {
                'chapter_id': chapterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：章节聚合（镜头、实体、关键帧 / 视频与最近任务状态）
     * @returns ApiResponse_CreatorBoardRead_ Successful Response
     * @throws ApiError
     */
    public static getCreatorBoardApiApiV1StudioChaptersChapterIdCreatorBoardGet({
        chapterId,
    }: {
        chapterId: string,
    }): CancelablePromise<ApiResponse_CreatorBoardRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/chapters/{chapter_id}/creator-board',
            path: {
                'chapter_id': chapterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
