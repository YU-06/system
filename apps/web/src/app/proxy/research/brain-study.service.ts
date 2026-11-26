import type {
  BrainStudyDto,
  BrainStudyListInput,
  ResearchCommandInput,
  UpdateBrainStudyInput,
} from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class BrainStudyService {
  private restService = inject(RestService);
  apiName = 'Default';
  archive = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, BrainStudyDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/brain-study/${id}/archive`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  delete = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, void>(
      {
        method: 'DELETE',
        url: `/api/app/brain-study/${id}`,
        params: { concurrencyStamp: input.concurrencyStamp },
      },
      { apiName: this.apiName, ...config },
    );
  deleteGroundTruth = (
    id: string,
    input: ResearchCommandInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, void>(
      {
        method: 'DELETE',
        url: `/api/app/brain-study/${id}/ground-truth`,
        params: { concurrencyStamp: input.concurrencyStamp },
      },
      { apiName: this.apiName, ...config },
    );
  downloadGroundTruth = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, Blob>(
      {
        method: 'POST',
        responseType: 'blob',
        headers: { Accept: 'application/octet-stream' },
        url: `/api/app/brain-study/${id}/download-ground-truth`,
      },
      { apiName: this.apiName, ...config },
    );
  get = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, BrainStudyDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: `/api/app/brain-study/${id}`,
      },
      { apiName: this.apiName, ...config },
    );
  getList = (
    input: BrainStudyListInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, PagedResultDto<BrainStudyDto>>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/brain-study',
        params: {
          status: input.status,
          filter: input.filter,
          sorting: input.sorting,
          skipCount: input.skipCount,
          maxResultCount: input.maxResultCount,
        },
      },
      { apiName: this.apiName, ...config },
    );
  registerGroundTruth = (
    id: string,
    input: FormData,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config> & {
      reportProgress?: boolean;
    },
  ) =>
    this.restService.request<unknown, BrainStudyDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/brain-study/${id}/register-ground-truth`,
        body: input,
        reportProgress: config?.reportProgress,
      },
      { apiName: this.apiName, ...config },
    );
  update = (
    id: string,
    input: UpdateBrainStudyInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, BrainStudyDto>(
      {
        method: 'PUT',
        headers: { Accept: 'application/json' },
        url: `/api/app/brain-study/${id}`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  upload = (
    input: FormData,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config> & {
      reportProgress?: boolean;
    },
  ) =>
    this.restService.request<unknown, BrainStudyDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: '/api/app/brain-study/upload',
        body: input,
        reportProgress: config?.reportProgress,
      },
      { apiName: this.apiName, ...config },
    );
}
