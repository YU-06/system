import type { FullAuditedEntityDto, PagedAndSortedResultRequestDto } from '@abp/ng.core';
import type { BrainStudyStatus } from './brain-study-status.enum';
import type { ModelArchitecture } from './model-architecture.enum';
import type { SegmentationJobStatus } from './segmentation-job-status.enum';
import type { IRemoteStreamContent } from '../volo/abp/content/models';
export interface BrainStudyDto extends FullAuditedEntityDto<string> {
  studyNumber?: string;
  pseudonym?: string;
  modality?: string;
  originalFileObjectKey?: string;
  originalFileSha256?: string;
  groundTruthSha256?: string | null;
  hasGroundTruth?: boolean;
  width?: number;
  height?: number;
  sliceIndex?: number;
  status?: BrainStudyStatus;
  jobRequestCount?: number;
  concurrencyStamp?: string;
}
export interface BrainStudyListInput extends ResearchListInput {
  status?: BrainStudyStatus | null;
}
export interface ChangeModelStateInput extends ResearchCommandInput {
  isActive?: boolean;
  isDefault?: boolean;
}
export interface CreateExperimentRunInput {
  experimentName: string;
  configHash: string;
  gitCommit: string;
  datasetSplitHash: string;
  randomSeed?: number;
  modelVersionId?: string;
  metricsJson: string;
  artifactObjectKey: string;
}
export interface CreateModelVersionInput {
  name: string;
  architecture?: ModelArchitecture;
  semanticVersion: string;
  weightObjectKey: string;
  weightSha256: string;
  threshold?: number;
  metricsJson: string;
}
export interface CreateSegmentationJobInput {
  studyId?: string;
  modelVersionId?: string;
  idempotencyKey: string;
}
export interface ExperimentRunDto extends FullAuditedEntityDto<string> {
  experimentName?: string;
  configHash?: string;
  gitCommit?: string;
  datasetSplitHash?: string;
  randomSeed?: number;
  modelVersionId?: string;
  metricsJson?: string;
  artifactObjectKey?: string;
  createdTime?: string;
  concurrencyStamp?: string;
}
export interface ExperimentRunListInput extends ResearchListInput {
  modelVersionId?: string | null;
  randomSeed?: number | null;
}
export interface ModelVersionDto extends FullAuditedEntityDto<string> {
  name?: string;
  architecture?: ModelArchitecture;
  semanticVersion?: string;
  preprocessingVersion?: string;
  weightObjectKey?: string;
  weightSha256?: string;
  inputSize?: number;
  threshold?: number;
  metricsJson?: string;
  isActive?: boolean;
  isDefault?: boolean;
  publishedTime?: string | null;
  concurrencyStamp?: string;
}
export interface ModelVersionListInput extends ResearchListInput {
  architecture?: ModelArchitecture | null;
  isActive?: boolean | null;
}
export interface ResearchCommandInput {
  concurrencyStamp: string;
}
export interface ResearchListInput extends PagedAndSortedResultRequestDto {
  filter?: string | null;
}
export interface SegmentationJobDto extends FullAuditedEntityDto<string> {
  studyId?: string;
  modelVersionId?: string;
  inputSha256?: string | null;
  architecture?: ModelArchitecture | null;
  modelSemanticVersion?: string | null;
  preprocessingVersion?: string | null;
  weightSha256?: string | null;
  inputSize?: number | null;
  threshold?: number | null;
  requesterId?: string;
  idempotencyKey?: string;
  status?: SegmentationJobStatus;
  progress?: number;
  correlationId?: string;
  requestedTime?: string;
  startedTime?: string | null;
  completedTime?: string | null;
  leaseExpiresAt?: string | null;
  errorCode?: string | null;
  errorMessage?: string | null;
  retryCount?: number;
  concurrencyStamp?: string;
}
export interface SegmentationJobListInput extends ResearchListInput {
  studyId?: string | null;
  modelVersionId?: string | null;
  status?: SegmentationJobStatus | null;
}
export interface SegmentationResultDto extends FullAuditedEntityDto<string> {
  jobId?: string;
  maskObjectKey?: string;
  maskSha256?: string | null;
  overlayObjectKey?: string | null;
  contourObjectKey?: string | null;
  remotePredictionSha256?: string | null;
  groundTruthSha256?: string | null;
  evaluationProtocol?: string | null;
  dice?: number | null;
  ioU?: number | null;
  precision?: number | null;
  recall?: number | null;
  tumorAreaPixels?: number;
  tumorAreaRatio?: number;
  inferenceMilliseconds?: number;
  preprocessingMilliseconds?: number;
  postprocessingMilliseconds?: number;
  createdTime?: string;
  concurrencyStamp?: string;
}
export interface SegmentationResultListInput extends ResearchListInput {
  jobId?: string | null;
}
export interface UpdateBrainStudyInput extends ResearchCommandInput {
  pseudonym: string;
}
export interface UploadBrainStudyInput {
  studyNumber: string;
  pseudonym: string;
  sliceIndex?: number;
  file: IRemoteStreamContent;
}
export interface UploadGroundTruthInput {
  file: IRemoteStreamContent;
}
