/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 前端据此决定走直传还是经函数上传。
 */
export type DirectUploadCapabilitiesRead = {
    /**
     * 可用的直传后端：vercel_blob（客户端令牌）或 s3（预签名 PUT，含 R2）；None 表示只能经函数上传
     */
    direct?: (string | null);
    /**
     * 经函数上传的建议大小上限（字节）
     */
    max_server_upload_bytes: number;
    /**
     * 直传大小上限（字节）
     */
    max_direct_upload_bytes: number;
};

