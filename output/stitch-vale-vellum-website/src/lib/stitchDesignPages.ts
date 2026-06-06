import { stitchNativeContent } from './stitchNativeContent';

export const stitchDesignPages = stitchNativeContent.pages;
export const stitchDesignMeta = stitchNativeContent.meta;
export type StitchPageId = keyof typeof stitchNativeContent.pages;
