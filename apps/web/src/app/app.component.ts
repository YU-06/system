import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideActivity,
  lucideArrowUpRight,
  lucideFlaskConical,
  lucideShieldCheck,
} from '@ng-icons/lucide';
import { I18nService } from './localization/i18n.service';
import { ResearchAccessService } from './shared/research-access.service';

@Component({
  selector: 'app-root',
  imports: [AsyncPipe, RouterOutlet, RouterLink, RouterLinkActive, NgIcon],
  providers: [
    provideIcons({ lucideActivity, lucideArrowUpRight, lucideFlaskConical, lucideShieldCheck }),
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="skip-link" href="#main-content">{{ text.skipToContent }}</a>
    <div class="app-shell">
      <aside class="sidebar">
        <a class="brand" routerLink="/" [attr.aria-label]="text.brand">
          <img src="/assets/brainseg-mark.png" width="40" height="40" [alt]="text.brandImageAlt" />
          <span
            ><strong>{{ text.brand }}</strong
            ><small>{{ text.brandCaption }}</small></span
          >
        </a>
        <div class="sidebar-label">{{ text.workspace }}</div>
        <nav [attr.aria-label]="text.navigation">
          <a
            routerLink="/"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            ariaCurrentWhenActive="page"
            [attr.aria-label]="text.overview"
            [title]="text.overview"
          >
            <ng-icon name="lucideActivity" aria-hidden="true" />
            <span>{{ text.overview }}</span>
          </a>
          <a
            href="/swagger/index.html"
            target="_blank"
            rel="noopener"
            [attr.aria-label]="text.apiDocs"
            [title]="text.apiDocs"
          >
            <ng-icon name="lucideArrowUpRight" aria-hidden="true" />
            <span>{{ text.apiDocs }}</span>
          </a>
          @if (canStudies$ | async) {
            <a routerLink="/studies" routerLinkActive="active" ariaCurrentWhenActive="page">
              <ng-icon name="lucideActivity" aria-hidden="true" />
              <span>{{ text.studiesTitle }}</span>
            </a>
          }
          @if (canJobs$ | async) {
            <a routerLink="/jobs" routerLinkActive="active" ariaCurrentWhenActive="page">
              <ng-icon name="lucideActivity" aria-hidden="true" />
              <span>{{ text.jobsTitle }}</span>
            </a>
          }
          @if (canModels$ | async) {
            <a routerLink="/models" routerLinkActive="active" ariaCurrentWhenActive="page">
              <ng-icon name="lucideActivity" aria-hidden="true" />
              <span>{{ text.modelsTitle }}</span>
            </a>
          }
          @if (canExperiments$ | async) {
            <a routerLink="/experiments" routerLinkActive="active" ariaCurrentWhenActive="page">
              <ng-icon name="lucideFlaskConical" aria-hidden="true" />
              <span>{{ text.experimentsTitle }}</span>
            </a>
          }
        </nav>
        <div class="sidebar-foot">
          <ng-icon name="lucideFlaskConical" aria-hidden="true" />
          <span
            >{{ text.development }}<small>{{ text.version }}</small></span
          >
        </div>
      </aside>
      <div class="workspace">
        <header class="topbar">
          <span>{{ text.brandCaption }}</span>
          @if (access.state() === 'unavailable') {
            <span class="error-note" role="alert">{{ text.permissionsUnavailable }}</span>
          }
          <span class="research-badge"
            ><ng-icon name="lucideFlaskConical" aria-hidden="true" />{{ text.researchOnly }}</span
          >
        </header>
        <main id="main-content" tabindex="-1"><router-outlet /></main>
      </div>
      <footer class="disclaimer" role="note">
        <ng-icon name="lucideShieldCheck" aria-hidden="true" />
        <span>{{ text.researchDisclaimer }}</span>
      </footer>
    </div>
  `,
})
export class AppComponent {
  readonly text = inject(I18nService).text;
  readonly access = inject(ResearchAccessService);
  readonly canStudies$ = this.access.can$('BrainSeg.BrainStudies');
  readonly canJobs$ = this.access.can$('BrainSeg.SegmentationJobs');
  readonly canModels$ = this.access.can$('BrainSeg.ModelVersions');
  readonly canExperiments$ = this.access.can$('BrainSeg.ExperimentRuns');
}
