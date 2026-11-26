import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { map } from 'rxjs';
import { ResearchAccessService } from './research-access.service';

export const researchPermissionGuard: CanActivateFn = (route) => {
  const router = inject(Router);
  const configuredPolicies = route.data['requiredPolicies'];
  let policies: string[];
  if (configuredPolicies !== undefined) {
    if (
      !Array.isArray(configuredPolicies) ||
      !configuredPolicies.length ||
      !configuredPolicies.every((policy): policy is string => typeof policy === 'string')
    ) {
      return router.createUrlTree(['/access-denied']);
    }
    policies = configuredPolicies;
  } else if (typeof route.data['requiredPolicy'] === 'string') {
    policies = [route.data['requiredPolicy']];
  } else {
    return true;
  }
  if (!policies.length) return true;

  const access = inject(ResearchAccessService);
  return access
    .canAll$(policies)
    .pipe(map((granted) => (granted ? true : router.createUrlTree(['/access-denied']))));
};
