import { mapEnumToOptions } from '@abp/ng.core';
export enum SegmentationJobStatus {
  Pending = 'Pending',
  Running = 'Running',
  Succeeded = 'Succeeded',
  Failed = 'Failed',
  Cancelled = 'Cancelled',
}
export const segmentationJobStatusOptions = mapEnumToOptions(SegmentationJobStatus);
