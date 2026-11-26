import { mapEnumToOptions } from '@abp/ng.core';
export enum BrainStudyStatus {
  Uploaded = 'Uploaded',
  Ready = 'Ready',
  Archived = 'Archived',
}
export const brainStudyStatusOptions = mapEnumToOptions(BrainStudyStatus);
