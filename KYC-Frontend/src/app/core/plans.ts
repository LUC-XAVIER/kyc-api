/** The four subscription plans (mirrors the backend seed). */
export interface Plan {
  key: 'STARTER' | 'GROWTH' | 'PRO' | 'ENTERPRISE';
  name: string;
  tagline: string;
  price: string;
  period: string;
  volume: string;
  popular: boolean;
  features: string[];
}

export const PLANS: Plan[] = [
  { key: 'STARTER', name: 'Starter', tagline: 'For single-branch MFIs and pilots', price: '25,000', period: 'FCFA/mo', volume: '200 verifications / month', popular: false, features: ['Dashboard for 1 branch', 'Up to 3 agent accounts', 'Face match + liveness + OCR', 'Duplicate detection', 'Monthly compliance report', 'Email support'] },
  { key: 'GROWTH', name: 'Growth', tagline: 'For multi-branch MFIs', price: '65,000', period: 'FCFA/mo', volume: '1,000 verifications / month', popular: false, features: ['Dashboard for up to 5 branches', 'Up to 15 agent accounts', 'Everything in Starter', 'On-demand compliance reports', 'API access for integration', 'Priority email support'] },
  { key: 'PRO', name: 'Pro', tagline: 'For established MFI networks', price: '150,000', period: 'FCFA/mo', volume: '5,000 verifications / month', popular: true, features: ['Unlimited branches', 'Unlimited agent accounts', 'Everything in Growth', 'Custom rate limits', 'Dedicated API key with higher throughput', 'Phone + email support, 24h response', 'Quarterly model performance review'] },
  { key: 'ENTERPRISE', name: 'Enterprise', tagline: 'For networks and federations', price: 'Custom', period: '', volume: '10,000+ verifications / month', popular: false, features: ['Everything in Pro', 'Volume-based custom pricing', 'Dedicated infrastructure option', 'Custom OCR tuning for partner documents', 'SLA-backed uptime guarantee', 'Dedicated account manager'] },
];
