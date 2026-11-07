/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 镜头对白行（已确认）；带行 ID 以便在分镜卡里直接增删改。
 */
export type CreatorDialogueLineRead = {
    /**
     * 对白行 ID（ShotDialogLine.id）
     */
    id: number;
    /**
     * 说话角色名；旁白为空
     */
    speaker: string;
    /**
     * 说话角色 ID（已关联到角色时）
     */
    speaker_character_id: (string | null);
    /**
     * 台词
     */
    text: string;
};

