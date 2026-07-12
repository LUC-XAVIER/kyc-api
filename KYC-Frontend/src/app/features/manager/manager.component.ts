import { Component } from '@angular/core';

/**
 * Manager application shell (Dashboard / Review queue / History / Reports /
 * Agents / API keys / Settings / Pricing). Ported from
 * design-reference/MFI-Manager.dc.html in a later slice; placeholder for now.
 */
@Component({
  selector: 'app-manager',
  template: `
    <div class="placeholder">
      <h1>Manager app</h1>
      <p>
        Dashboard · Review queue · History · Reports · Agents · API keys ·
        Settings — coming next.
      </p>
    </div>
  `,
  styles: [
    `
      .placeholder {
        padding: 48px;
        color: var(--ox-muted);
      }
      h1 {
        color: var(--ox-text);
      }
    `,
  ],
})
export class ManagerComponent {}
