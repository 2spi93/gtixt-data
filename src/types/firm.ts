/**
 * Firm Type Definition
 * Represents a financial services firm
 */

export interface Firm {
  firm_id: string;
  name: string;
  score?: number;
  status?: string;
  country?: string;
  sector?: string;
  website?: string;
  website_root?: string;
  registration_number?: string;
  na_rate?: number;
  pillar_scores?: Record<string, number>;
  address?: {
    street?: string;
    city?: string;
    postcode?: string;
    country?: string;
  };
  contact?: {
    email?: string;
    phone?: string;
  };
}
