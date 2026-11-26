import type {
  ResearchCommandInput,
  SegmentationResultDto,
  SegmentationResultListInput,
} from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class SegmentationResultService {
  private restService = inject(RestService);
  apiName = 'Default';
  downloadMask = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, Blob>(
      {
        method: 'POST',
        responseType: 'blob',
        headers: { Accept: 'application/octet-stream' },
        url: `/api/app/segmentation-result/${id}/download-mask`,
      },
      { apiName: this.apiName, ...config },
    );
  evaluate = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, SegmentationResultDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/segmentation-result/${id}/evaluate`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  get = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, SegmentationResultDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: `/api/app/segmentation-result/${id}`,
      },
      { apiName: this.apiName, ...config },
    );
  getList = (
    input: SegmentationResultListInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, PagedResultDto<SegmentationResultDto>>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/segmentation-result',
        params: {
          jobId: input.jobId,
          filter: input.filter,
          sorting: input.sorting,
          skipCount: input.skipCount,
          maxResultCount: input.maxResultCount,
        },
      },
      { apiName: this.apiName, ...config },
    );
}
