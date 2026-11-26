import {
  PermissionService,
  AbpApplicationConfigurationService,
  ConfigStateService,
} from '@abp/ng.core';
import { Injectable, inject, signal } from '@angular/core';
import {
  catchError,
  forkJoin,
  map,
  of,
  shareReplay,
  switchMap,
  take,
  tap,
  type Observable,
} from 'rxjs';

export type AccessState = 'loading' | 'ready' | 'unavailable';

@Injectable({ providedIn: 'root' })
export class ResearchAccessService {
  private readonly configuration = inject(AbpApplicationConfigurationService);
  private readonly configState = inject(ConfigStateService);
  private readonly permissions = inject(PermissionService);
  readonly state = signal<AccessState>('loading');

  private readonly configurationLoaded = this.configuration
    .get({ includeLocalizationResources: false }, { skipHandleError: true })
    .pipe(
      tap((value) => {
        this.configState.setState(value);
        this.state.set('ready');
      }),
      map(() => true),
      catchError(() => {
        this.state.set('unavailable');
        return of(false);
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );

  can$(policy: string): Observable<boolean> {
    return this.configurationLoaded.pipe(
      switchMap((loaded) =>
        loaded ? this.permissions.getGrantedPolicy$(policy).pipe(take(1)) : of(false),
      ),
      catchError(() => {
        this.state.set('unavailable');
        return of(false);
      }),
    );
  }

  canAll$(policies: readonly string[]): Observable<boolean> {
    return policies.length
      ? forkJoin(policies.map((policy) => this.can$(policy))).pipe(
          map((granted) => granted.every(Boolean)),
        )
      : of(true);
  }
}
