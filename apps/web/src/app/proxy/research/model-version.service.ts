import type {
  ChangeModelStateInput,
  CreateModelVersionInput,
  ModelVersionDto,
  ModelVersionListInput,
} from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class ModelVersionService {
  private restService = inject(RestService);
  apiName = 'Default';
  create = (
    input: CreateModelVersionInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, ModelVersionDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: '/api/app/model-version',
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  get = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, ModelVersionDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: `/api/app/model-version/${id}`,
      },
      { apiName: this.apiName, ...config },
    );
  getList = (
    input: ModelVersionListInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, PagedResultDto<ModelVersionDto>>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/model-version',
        params: {
          architecture: input.architecture,
          isActive: input.isActive,
          filter: input.filter,
          sorting: input.sorting,
          skipCount: input.skipCount,
          maxResultCount: input.maxResultCount,
        },
      },
      { apiName: this.apiName, ...config },
    );
  setState = (
    id: string,
    input: ChangeModelStateInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, ModelVersionDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: `/api/app/model-version/${id}/set-state`,
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
}
