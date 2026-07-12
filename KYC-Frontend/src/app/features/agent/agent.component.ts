import { Component } from '@angular/core';

/**
 * Agent application shell (sidebar + New Verification / My Submissions /
 * Profile screens). Ported from design-reference/Agent.dc.html in the next
 * slice; a placeholder for now so routing is navigable.
 */
@Component({
  selector: 'app-agent',
  template: `
    <div class="placeholder">
      <h1>Agent app</h1>
      <p>New Verification · My Submissions · Profile — coming next.</p>
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
export class AgentComponent {}
