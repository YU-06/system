import type { CreateExperimentRunInput, ExperimentRunDto, ExperimentRunListInput } from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class ExperimentRunService {
  private restService = inject(RestService);
  apiName = 'Default';
  create = (
    input: CreateExperimentRunInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, ExperimentRunDto>(
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        url: '/api/app/experiment-run',
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
  get = (id: string, cancellationToken?: unknown, config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, ExperimentRunDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: `/api/app/experiment-run/${id}`,
      },
      { apiName: this.apiName, ...config },
    );
  getList = (
    input: ExperimentRunListInput,
    cancellationToken?: unknown,
    config?: Partial<Rest.Config>,
  ) =>
    this.restService.request<unknown, PagedResultDto<ExperimentRunDto>>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/experiment-run',
        params: {
          modelVersionId: input.modelVersionId,
          randomSeed: input.randomSeed,
          filter: input.filter,
          sorting: input.sorting,
          skipCount: input.skipCount,
          maxResultCount: input.maxResultCount,
        },
      },
      { apiName: this.apiName, ...config },
    );
}
