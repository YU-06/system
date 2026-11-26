import { TestBed } from '@angular/core/testing';
import {
  AbpApplicationConfigurationService,
  ConfigStateService,
  PermissionService,
} from '@abp/ng.core';
import { firstValueFrom, of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { ResearchAccessService } from './research-access.service';

describe('ResearchAccessService', () => {
  it('grants only policies returned by ABP configuration', async () => {
    const grantedPolicies: Record<string, boolean> = {
      'BrainSeg.BrainStudies': true,
      'BrainSeg.BrainStudies.Create': true,
    };
    const configuration = { auth: { grantedPolicies } };
    const setState = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: AbpApplicationConfigurationService,
          useValue: { get: () => of(configuration) },
        },
        { provide: ConfigStateService, useValue: { setState } },
        {
          provide: PermissionService,
          useValue: {
            getGrantedPolicy$: (policy: string) => of(grantedPolicies[policy] ?? false),
          },
        },
      ],
    });
    const access = TestBed.inject(ResearchAccessService);

    await expect(firstValueFrom(access.can$('BrainSeg.BrainStudies'))).resolves.toBe(true);
    await expect(firstValueFrom(access.can$('BrainSeg.ModelVersions'))).resolves.toBe(false);
    await expect(
      firstValueFrom(access.canAll$(['BrainSeg.BrainStudies', 'BrainSeg.BrainStudies.Create'])),
    ).resolves.toBe(true);
    await expect(
      firstValueFrom(access.canAll$(['BrainSeg.BrainStudies', 'BrainSeg.ModelVersions'])),
    ).resolves.toBe(false);
    expect(setState).toHaveBeenCalledOnce();
  });

  it('fails closed when ABP application configuration is unavailable', async () => {
    TestBed.configureTestingModule({
      providers: [
        {
          provide: AbpApplicationConfigurationService,
          useValue: { get: () => throwError(() => new Error('unavailable')) },
        },
        { provide: ConfigStateService, useValue: { setState: vi.fn() } },
        { provide: PermissionService, useValue: { getGrantedPolicy$: () => of(true) } },
      ],
    });
    const access = TestBed.inject(ResearchAccessService);

    await expect(firstValueFrom(access.can$('BrainSeg.BrainStudies.Create'))).resolves.toBe(false);
    expect(access.state()).toBe('unavailable');
  });
});
