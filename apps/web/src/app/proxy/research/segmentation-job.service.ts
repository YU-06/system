import type {
  CreateSegmentationJobInput,
  ResearchCommandInput,
  SegmentationJobDto,
  SegmentationJobListInput,
} from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class SegmentationJobService {
  private restService = inject(RestService);
  apiName = 'Default';
  cancel = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, SegmentationJobDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/segmentation-job/${id}/cancel`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  create = (
    input: CreateSegmentationJobInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, SegmentationJobDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: '/api/app/segmentation-job',
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  get = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, SegmentationJobDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: `/api/app/segmentation-job/${id}`,
      },
      { apiName: this.apiName, ...config },
    );
  getList = (
    input: SegmentationJobListInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, PagedResultDto<SegmentationJobDto>>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/segmentation-job',
        params: {
          studyId: input.studyId,
          modelVersionId: input.modelVersionId,
          status: input.status,
          filter: input.filter,
          sorting: input.sorting,
          skipCount: input.skipCount,
          maxResultCount: input.maxResultCount,
        },
      },
      { apiName: this.apiName, ...config },
    );
  retry = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, SegmentationJobDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/segmentation-job/${id}/retry`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
}
