import { DISABLE_PROJECT_NAME, provideAbpCore, withOptions } from '@abp/ng.core';
import { registerLocaleData } from '@angular/common';
import localeZh from '@angular/common/locales/zh';
import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, LOCALE_ID, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { environment } from '../environments/environment';
import { SystemComponent } from './features/system/system.component';
import uiText from './localization/zh-Hans.json';

registerLocaleData(localeZh);

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    provideRouter([
      { path: '', component: SystemComponent, title: uiText.brand },
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
