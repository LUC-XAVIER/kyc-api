/** Full-screen branded loading state shown between pages. */

import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { LoadingService } from '../core/loading.service';

@Component({
  selector: 'app-loading-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading.visible()) {
      <div class="splash" role="status" aria-live="polite">
        <div class="splash__bar"></div>
        <div class="splash__mark">K</div>
        <span class="splash__sr">Loading</span>
      </div>
    }
  `,
  styles: `
    .splash {
      position: fixed;
      inset: 0;
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--ox-bg);
      animation: splash-in 160ms ease-out;
    }

    /* The admin dashboard sets .admin-dark on the document root while it is
       mounted; match its dark backdrop so the splash isn't a white flash.
       The K mark stays red-on-white in both themes. */
    :host-context(.admin-dark) .splash {
      background: #0b0e14;
    }

    /* Indeterminate sliver across the top — the progress cue, since we
       cannot know how far along a lazy chunk download actually is. */
    .splash__bar {
      position: absolute;
      top: 0;
      left: 0;
      height: 3px;
      width: 40%;
      background: var(--ox-red);
      animation: splash-sweep 1.1s ease-in-out infinite;
    }

    .splash__mark {
      width: 56px;
      height: 56px;
      border-radius: 14px;
      background: var(--ox-red);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      font-weight: 700;
      animation: splash-pulse 1.1s ease-in-out infinite;
    }

    .splash__sr {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }

    @keyframes splash-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    @keyframes splash-sweep {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(250%); }
    }

    @keyframes splash-pulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(0.88); opacity: 0.65; }
    }

    /* Respect a user who has asked the OS for less motion. */
    @media (prefers-reduced-motion: reduce) {
      .splash,
      .splash__bar,
      .splash__mark {
        animation: none;
      }
    }
  `,
})
export class LoadingOverlayComponent {
  readonly loading = inject(LoadingService);
}
