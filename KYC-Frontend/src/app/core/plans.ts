/** The four subscription plans (mirrors the backend seed). */
export interface Plan {
  key: 'STARTER' | 'GROWTH' | 'PRO' | 'ENTERPRISE';
  name: string;
  tagline: string;
  price: string;
  period: string;
  /** Monthly price × 12, shown for reference. Omitted for custom pricing. */
  yearly?: string;
  volume: string;
  popular: boolean;
  features: string[];
}

export const PLANS: Plan[] = [
  { key: 'STARTER', name: 'Starter', tagline: 'For single-branch MFIs and pilots', price: '$40', period: '/mo', yearly: '$480 / year', volume: '200 verifications / month', popular: false, features: ['Can create 1 branch', 'Up to 3 agent accounts', 'Face match + liveness + OCR', 'Duplicate detection', 'Monthly compliance report', 'Email support'] },
  { key: 'GROWTH', name: 'Growth', tagline: 'For multi-branch MFIs', price: '$105', period: '/mo', yearly: '$1,260 / year', volume: '1,000 verifications / month', popular: false, features: ['Can create up to 5 branches', 'Up to 15 agent accounts', 'Everything in Starter', 'On-demand compliance reports', 'API access for integration', 'Priority email support'] },
  { key: 'PRO', name: 'Pro', tagline: 'For established MFI networks', price: '$245', period: '/mo', yearly: '$2,940 / year', volume: '5,000 verifications / month', popular: true, features: ['Unlimited branches', 'Unlimited agent accounts', 'Everything in Growth', 'Phone + email support, 24h response'] },
  { key: 'ENTERPRISE', name: 'Enterprise', tagline: 'For networks and federations', price: 'Custom', period: '', volume: '10,000+ verifications / month', popular: false, features: ['Everything in Pro', 'Volume-based custom pricing', 'Dedicated infrastructure option', 'Custom OCR tuning for partner documents', 'SLA-backed uptime guarantee', 'Dedicated account manager'] },
];
