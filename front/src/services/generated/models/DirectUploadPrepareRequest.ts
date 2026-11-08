/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DirectUploadPrepareRequest = {
    filename: string;
    /**
     * 浏览器给出的 MIME 类型；S3 模式参与预签名，PUT 时必须原样携带
     */
    content_type?: (string | null);
};

