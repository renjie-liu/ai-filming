/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 由部署环境自动配置的供应商（API Key 来自环境变量，无需在界面填写）。
 */
export type SetupProviderRead = {
    /**
     * 供应商 ID
     */
    id: string;
    /**
     * 展示名称，例如 Seedance · BytePlus ModelArk
     */
    label: string;
    /**
     * 区域：byteplus / volcengine
     */
    region?: (string | null);
    /**
     * API Key 是否由部署环境变量提供并在启动时同步
     */
    managed_by_deployment: boolean;
};

