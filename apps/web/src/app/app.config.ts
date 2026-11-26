import { DISABLE_PROJECT_NAME, provideAbpCore, withOptions } from '@abp/ng.core';
import { registerLocaleData } from '@angular/common';
import localeZh from '@angular/common/locales/zh';
import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, LOCALE_ID, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { environment } from '../environments/environment';
import { ExperimentComponent } from './features/experiment/experiment.component';
import { JobDetailComponent, JobListComponent } from './features/job/job.component';
import { ModelComponent } from './features/model/model.component';
import { ResultComponent } from './features/result/result.component';
import { StudyComponent } from './features/study/study.component';
import { AccessDeniedComponent } from './shared/access-denied.component';
import { researchPermissionGuard } from './shared/research-permission.guard';
import { SystemComponent } from './features/system/system.component';
import uiText from './localization/zh-Hans.json';

registerLocaleData(localeZh);

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    provideRouter([
      { path: '', component: SystemComponent, title: uiText.brand },
      {
        path: 'studies',
        component: StudyComponent,
        canActivate: [researchPermissionGuard],
        data: { requiredPolicy: 'BrainSeg.BrainStudies' },
        title: uiText.studiesTitle,
      },
      {
        path: 'jobs',
        component: JobListComponent,
        canActivate: [researchPermissionGuard],
        data: { requiredPolicy: 'BrainSeg.SegmentationJobs' },
        title: uiText.jobsTitle,
      },
      {
        path: 'jobs/:id',
        component: JobDetailComponent,
        canActivate: [researchPermissionGuard],
        data: { requiredPolicy: 'BrainSeg.SegmentationJobs' },
        title: uiText.jobDetailTitle,
      },
      {
        path: 'results/:id',
        component: ResultComponent,
        canActivate: [researchPermissionGuard],
        data: {
          requiredPolicies: [
            'BrainSeg.SegmentationResults',
            'BrainSeg.SegmentationResults.Download',
          ],
        },
        title: uiText.resultTitle,
      },
      {
        path: 'models',
        component: ModelComponent,
        canActivate: [researchPermissionGuard],
        data: { requiredPolicy: 'BrainSeg.ModelVersions' },
        title: uiText.modelsTitle,
      },
      {
        path: 'experiments',
        component: ExperimentComponent,
        canActivate: [researchPermissionGuard],
        data: { requiredPolicy: 'BrainSeg.ExperimentRuns' },
        title: uiText.experimentsTitle,
      },
      { path: 'access-denied', component: AccessDeniedComponent, title: uiText.accessDeniedTitle },
      { path: '**', redirectTo: '' },
    ]),
    provideAbpCore(
      withOptions({
        environment,
        registerLocaleFn: () => Promise.resolve(),
        skipGetAppConfiguration: true,
        skipInitAuthService: true,
      }),
    ),
    { provide: LOCALE_ID, useValue: 'zh-Hans' },
    { provide: DISABLE_PROJECT_NAME, useValue: true },
  ],
};
