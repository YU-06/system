import { mapEnumToOptions } from '@abp/ng.core';
export enum ModelArchitecture {
  UNet = 'UNet',
  AttentionUNet = 'AttentionUNet',
}
export const modelArchitectureOptions = mapEnumToOptions(ModelArchitecture);
