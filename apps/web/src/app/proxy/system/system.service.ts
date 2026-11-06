import type { SystemStatusDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';
@Injectable({
  providedIn: 'root',
})
export class SystemService {
  private restService = inject(RestService);
  apiName = 'Default';
  get = (config?: Partial<Rest.Config>) =>
    this.restService.request<unknown, SystemStatusDto>(
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        url: '/api/app/system',
      },
      { apiName: this.apiName, ...config },
    );
}
