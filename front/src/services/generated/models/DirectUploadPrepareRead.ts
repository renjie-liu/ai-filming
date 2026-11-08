/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DirectUploadPrepareRead = {
    /**
     * 本次直传使用的后端：vercel_blob 或 s3
     */
    backend: string;
    /**
     * 登记时回传的存储 key
     */
    storage_key: string;
    /**
     * 对象路径；Blob 直传时作为 `upload()` 的 pathname
     */
    pathname: string;
    /**
     * s3：浏览器直接 PUT 的预签名 URL；vercel_blob 为空
     */
    upload_url?: (string | null);
    /**
     * s3：上传完成后的公网 URL，登记时原样回传；vercel_blob 为空
     */
    public_url?: (string | null);
    /**
     * s3：PUT 必须携带的请求头（Content-Type）
     */
    headers?: (Record<string, string> | null);
};

