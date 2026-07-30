import { fetchAPI } from '@panwatch/api'

import type {
  AssetPayload,
  PerformanceResponse,
  WealthAsset,
  WealthSnapshot,
  WealthSummary,
} from './types'

interface WealthSyncResult {
  asset_count: number
  snapshot_count: number
  as_of_date: string
  summary: WealthSummary
}

export const wealthApi = {
  summary: () => fetchAPI<WealthSummary>('/wealth/summary'),
  performance: (period: string) =>
    fetchAPI<PerformanceResponse>(`/wealth/performance?period=${encodeURIComponent(period)}`),
  createAsset: (payload: AssetPayload) =>
    fetchAPI<WealthAsset>('/wealth/assets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateAsset: (id: number, payload: AssetPayload) =>
    fetchAPI<WealthAsset>(`/wealth/assets/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteAsset: (id: number) =>
    fetchAPI<{ success: boolean }>(`/wealth/assets/${id}`, { method: 'DELETE' }),
  snapshot: () =>
    fetchAPI<WealthSnapshot>('/wealth/snapshots', {
      method: 'POST',
      body: JSON.stringify({}),
      timeoutMs: 45_000,
    }),
  syncRelay: () =>
    fetchAPI<WealthSyncResult>('/wealth/sync-relay', {
      method: 'POST',
      body: JSON.stringify({}),
      timeoutMs: 45_000,
    }),
}
