/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AttachedImageRead_ } from '../models/ApiResponse_AttachedImageRead_';
import type { ApiResponse_AttachedVideoRead_ } from '../models/ApiResponse_AttachedVideoRead_';
import type { ApiResponse_CreatorEntityCreatedRead_ } from '../models/ApiResponse_CreatorEntityCreatedRead_';
import type { ApiResponse_EntityShotsWrite_ } from '../models/ApiResponse_EntityShotsWrite_';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { CreatorEntityCreate } from '../models/CreatorEntityCreate';
import type { EntityShotsWrite } from '../models/EntityShotsWrite';
import type { FileAttachRequest } from '../models/FileAttachRequest';
import type { ShotEntityLinksWrite } from '../models/ShotEntityLinksWrite';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioCreatorService {
    /**
     * 创作模式：整体替换镜头「画面里会用到」的角色 / 场景 / 道具 / 服装
     * 为 None 的类型保持不变；移除的实体会把同名提取候选标记为 ignored，避免被自动确认挂回。
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static setShotLinksApiApiV1StudioCreatorShotsShotIdLinksPut({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: ShotEntityLinksWrite,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/studio/creator/shots/{shot_id}/links',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：设置实体在本章节内出现的镜头集合
     * @returns ApiResponse_EntityShotsWrite_ Successful Response
     * @throws ApiError
     */
    public static setEntityShotsApiApiV1StudioCreatorChaptersChapterIdEntitiesEntityTypeEntityIdShotsPut({
        chapterId,
        entityType,
        entityId,
        requestBody,
    }: {
        chapterId: string,
        entityType: string,
        entityId: string,
        requestBody: EntityShotsWrite,
    }): CancelablePromise<ApiResponse_EntityShotsWrite_> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/studio/creator/chapters/{chapter_id}/entities/{entity_type}/{entity_id}/shots',
            path: {
                'chapter_id': chapterId,
                'entity_type': entityType,
                'entity_id': entityId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：手动新增角色 / 场景 / 道具 / 服装并挂到镜头
     * @returns ApiResponse_CreatorEntityCreatedRead_ Successful Response
     * @throws ApiError
     */
    public static createChapterEntityApiApiV1StudioCreatorChaptersChapterIdEntitiesPost({
        chapterId,
        requestBody,
    }: {
        chapterId: string,
        requestBody: CreatorEntityCreate,
    }): CancelablePromise<ApiResponse_CreatorEntityCreatedRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/creator/chapters/{chapter_id}/entities',
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
     * 创作模式：把上传的图片设为角色形象 / 场景道具参考图
     * @returns ApiResponse_AttachedImageRead_ Successful Response
     * @throws ApiError
     */
    public static attachEntityImageApiApiV1StudioCreatorEntitiesEntityTypeEntityIdImageFromFilePost({
        entityType,
        entityId,
        requestBody,
    }: {
        entityType: string,
        entityId: string,
        requestBody: FileAttachRequest,
    }): CancelablePromise<ApiResponse_AttachedImageRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/creator/entities/{entity_type}/{entity_id}/image-from-file',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：把上传的图片设为镜头关键帧（首帧）
     * @returns ApiResponse_AttachedImageRead_ Successful Response
     * @throws ApiError
     */
    public static attachShotKeyframeApiApiV1StudioCreatorShotsShotIdKeyframeFromFilePost({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: FileAttachRequest,
    }): CancelablePromise<ApiResponse_AttachedImageRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/creator/shots/{shot_id}/keyframe-from-file',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创作模式：把上传的视频设为镜头成片
     * @returns ApiResponse_AttachedVideoRead_ Successful Response
     * @throws ApiError
     */
    public static attachShotVideoApiApiV1StudioCreatorShotsShotIdVideoFromFilePost({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: FileAttachRequest,
    }): CancelablePromise<ApiResponse_AttachedVideoRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/creator/shots/{shot_id}/video-from-file',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
