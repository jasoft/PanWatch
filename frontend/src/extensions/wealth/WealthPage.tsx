import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarCheck2,
  Landmark,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  TrendingUp,
  WalletCards,
} from 'lucide-react'

import { Button } from '@panwatch/base-ui/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@panwatch/base-ui/components/ui/dialog'
import { Input } from '@panwatch/base-ui/components/ui/input'
import { Label } from '@panwatch/base-ui/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@panwatch/base-ui/components/ui/select'
import { useToast } from '@panwatch/base-ui/components/ui/toast'

import { wealthApi } from './api'
import WealthChart from './WealthChart'
import type {
  AssetCategory,
  AssetPayload,
  PerformanceResponse,
  PositionSide,
  ValuationMethod,
  WealthAsset,
  WealthSummary,
} from './types'

const CATEGORY_OPTIONS: Array<{ value: AssetCategory; label: string }> = [
  { value: 'a_stock', label: 'A股' },
  { value: 'hk_stock', label: '港股' },
  { value: 'b_stock', label: 'B股' },
  { value: 'etf', label: 'ETF' },
  { value: 'public_fund', label: '公募基金' },
  { value: 'private_fund', label: '私募基金' },
  { value: 'cash', label: '现金' },
  { value: 'liability', label: '负债' },
  { value: 'future', label: '内盘期货' },
  { value: 'option', label: '期权' },
  { value: 'adjustment', label: '调整项' },
]

const PERIOD_OPTIONS = [
  { value: '1m', label: '1月' },
  { value: '3m', label: '3月' },
  { value: '6m', label: '6月' },
  { value: '1y', label: '1年' },
  { value: '3y', label: '3年' },
  { value: 'max', label: '全部' },
]

const emptyForm: AssetPayload = {
  account_name: '默认账户',
  category: 'a_stock',
  symbol: '',
  name: '',
  market: 'CN',
  currency: 'CNY',
  exchange_rate: 1,
  valuation_method: 'price',
  quantity: 0,
  current_price: null,
  cost_price: null,
  manual_amount: null,
  contract_multiplier: 1,
  position_side: 'long',
  margin: null,
  enabled: true,
  price_as_of: '',
}

const money = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY',
        maximumFractionDigits: 0,
      }).format(value)

const percent = (value: number | null | undefined, ratio = true) => {
  if (value == null) return '—'
  const normalized = ratio ? value * 100 : value
  return `${normalized >= 0 ? '+' : ''}${normalized.toFixed(2)}%`
}

const toNullableNumber = (value: string): number | null => {
  if (!value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const sourceLabel = (source: string) =>
  source.startsWith('google_sheets:') ? 'Google Sheets' : source === 'manual' ? '手工' : source

function MetricCard({
  title,
  value,
  note,
  tone = 'default',
}: {
  title: string
  value: string
  note: string
  tone?: 'default' | 'danger' | 'accent'
}) {
  const color =
    tone === 'danger'
      ? 'text-destructive'
      : tone === 'accent'
        ? 'text-primary'
        : 'text-foreground'
  return (
    <div className="card p-4 md:p-5">
      <div className="text-[12px] text-muted-foreground">{title}</div>
      <div className={`mt-2 text-[22px] md:text-[25px] font-semibold tracking-tight ${color}`}>
        {value}
      </div>
      <div className="mt-1.5 text-[11px] text-muted-foreground">{note}</div>
    </div>
  )
}

export default function WealthPage() {
  const { toast } = useToast()
  const [summary, setSummary] = useState<WealthSummary | null>(null)
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null)
  const [period, setPeriod] = useState('1y')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<AssetPayload>(emptyForm)

  const load = useCallback(async (targetPeriod = period) => {
    const [summaryData, performanceData] = await Promise.all([
      wealthApi.summary(),
      wealthApi.performance(targetPeriod),
    ])
    setSummary(summaryData)
    setPerformance(performanceData)
  }, [period])

  useEffect(() => {
    setLoading(true)
    load(period)
      .catch(error => toast(error instanceof Error ? error.message : '资产数据加载失败', 'error'))
      .finally(() => setLoading(false))
  }, [load, period, toast])

  const refresh = async () => {
    setRefreshing(true)
    try {
      await load(period)
      toast('资产数据已刷新', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '刷新失败', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const createSnapshot = async () => {
    setRefreshing(true)
    try {
      await wealthApi.snapshot()
      await load(period)
      toast('今日收盘市值快照已记录', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '快照记录失败', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const syncGoogleSheets = async () => {
    setRefreshing(true)
    try {
      await wealthApi.syncRelay()
      await load(period)
      toast('Google Sheets 当日资产已同步', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '表格同步失败', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const openCreate = () => {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEdit = (asset: WealthAsset) => {
    setEditingId(asset.id)
    setForm({
      account_name: asset.account_name,
      category: asset.category,
      symbol: asset.symbol,
      name: asset.name,
      market: asset.market,
      currency: asset.currency,
      exchange_rate: asset.exchange_rate,
      valuation_method: asset.valuation_method,
      quantity: asset.quantity,
      current_price: asset.current_price,
      cost_price: asset.cost_price,
      manual_amount: asset.manual_amount,
      contract_multiplier: asset.contract_multiplier,
      position_side: asset.position_side,
      margin: asset.margin,
      enabled: asset.enabled,
      price_as_of: asset.price_as_of,
    })
    setDialogOpen(true)
  }

  const saveAsset = async () => {
    if (!form.name.trim()) {
      toast('请填写资产名称', 'error')
      return
    }
    if (form.category === 'b_stock' && form.currency === 'CNY') {
      toast('B股必须选择 USD（沪B）或 HKD（深B）', 'error')
      return
    }
    setSaving(true)
    try {
      if (editingId) await wealthApi.updateAsset(editingId, form)
      else await wealthApi.createAsset(form)
      setDialogOpen(false)
      await load(period)
      toast(editingId ? '资产已更新' : '资产已添加', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const removeAsset = async (asset: WealthAsset) => {
    if (!window.confirm(`确认删除“${asset.name}”吗？`)) return
    try {
      await wealthApi.deleteAsset(asset.id)
      await load(period)
      toast('资产已删除', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '删除失败', 'error')
    }
  }

  const groupedAssets = useMemo(() => {
    const groups = new Map<string, WealthAsset[]>()
    for (const asset of summary?.assets || []) {
      const key = asset.category_label
      groups.set(key, [...(groups.get(key) || []), asset])
    }
    return [...groups.entries()]
  }, [summary])

  const latestPoint = performance?.points[performance.points.length - 1]
  const isPriceValuation = form.valuation_method === 'price'
  const isDerivative = form.valuation_method === 'derivative'

  if (loading && !summary) {
    return (
      <div className="max-w-7xl mx-auto py-20 flex items-center justify-center">
        <span className="w-7 h-7 border-2 border-primary/25 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5 md:space-y-6">
      <section className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
              <WalletCards className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-[20px] md:text-[24px] font-semibold tracking-tight">全资产</h1>
              <p className="text-[12px] md:text-[13px] text-muted-foreground mt-0.5">
                股票、基金、B股、现金、负债与衍生品统一人民币净值
              </p>
            </div>
          </div>
          {summary?.latest_sync && (
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              Google Sheets {summary.latest_sync.as_of_date} 已同步
              · {summary.latest_sync.asset_count} 项资产
              · {summary.latest_sync.snapshot_count} 条历史
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={syncGoogleSheets} disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            同步表格
          </Button>
          <Button variant="secondary" onClick={refresh} disabled={refreshing}>
            <RefreshCw className="w-4 h-4" />
            刷新
          </Button>
          <Button variant="secondary" onClick={createSnapshot} disabled={refreshing}>
            <CalendarCheck2 className="w-4 h-4" />
            记录今日
          </Button>
          <Button onClick={openCreate}>
            <Plus className="w-4 h-4" />
            添加资产
          </Button>
        </div>
      </section>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <MetricCard
          title="净资产"
          value={money(summary?.net_assets)}
          note={`总资产 ${money(summary?.gross_assets)}`}
          tone="accent"
        />
        <MetricCard
          title="负债"
          value={money(summary?.liabilities)}
          note={
            summary?.gross_assets
              ? `资产负债率 ${percent((summary.liabilities || 0) / summary.gross_assets)}`
              : '暂无负债'
          }
          tone="danger"
        />
        <MetricCard
          title="衍生品敞口"
          value={money(summary?.derivative_exposure)}
          note={`真实市值 ${money(summary?.real_market_value)}`}
        />
        <MetricCard
          title="杠杆率"
          value={summary ? `${summary.leverage.toFixed(2)}x` : '—'}
          note={`今日净值 ${percent(latestPoint?.daily_return)}`}
        />
      </section>

      <section className="card p-4 md:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
          <div>
            <h2 className="text-[15px] font-semibold flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              净值走势与基准
            </h2>
            <p className="text-[11px] text-muted-foreground mt-1">
              以区间首日归一化，组合使用份额净值，基准使用沪深300ETF收盘价
            </p>
          </div>
          <div className="flex rounded-xl border border-border bg-accent/20 p-1">
            {PERIOD_OPTIONS.map(option => (
              <button
                key={option.value}
                onClick={() => setPeriod(option.value)}
                className={`px-2.5 py-1.5 rounded-lg text-[11px] transition-all ${
                  period === option.value
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mb-4">
          {[
            ['组合收益', performance?.summary?.portfolio_return],
            ['沪深300ETF', performance?.summary?.benchmark_return],
            ['超额收益', performance?.summary?.excess_return],
          ].map(([label, rawValue]) => {
            const value = typeof rawValue === 'number' ? rawValue : null
            return (
              <div key={String(label)} className="rounded-xl bg-accent/25 px-3 py-2.5">
                <div className="text-[10px] text-muted-foreground">{label}</div>
                <div
                  className={`text-[15px] font-semibold mt-1 flex items-center gap-1 ${
                    value != null && value < 0 ? 'text-emerald-500' : 'text-rose-500'
                  }`}
                >
                  {value != null && value < 0
                    ? <ArrowDownRight className="w-3.5 h-3.5" />
                    : <ArrowUpRight className="w-3.5 h-3.5" />}
                  {percent(value)}
                </div>
              </div>
            )
          })}
        </div>
        <WealthChart data={performance?.points || []} />
      </section>

      <section className="card overflow-hidden">
        <div className="px-4 md:px-6 py-4 border-b border-border/60 flex items-center justify-between">
          <div>
            <h2 className="text-[15px] font-semibold flex items-center gap-2">
              <Landmark className="w-4 h-4 text-primary" />
              资产明细
            </h2>
            <p className="text-[11px] text-muted-foreground mt-1">
              B股、港股和美元资产均显示原币价格与人民币市值
            </p>
          </div>
          <span className="text-[11px] text-muted-foreground">
            {summary?.assets.length || 0} 项
          </span>
        </div>
        {!groupedAssets.length ? (
          <div className="py-16 text-center text-[13px] text-muted-foreground">
            暂无资产，点击“添加资产”开始
          </div>
        ) : (
          <div className="divide-y divide-border/60">
            {groupedAssets.map(([category, assets]) => (
              <div key={category}>
                <div className="px-4 md:px-6 py-2.5 bg-accent/20 flex items-center justify-between">
                  <span className="text-[12px] font-medium">{category}</span>
                  <span className="text-[11px] text-muted-foreground">
                    {money(assets.reduce((sum, asset) => sum + asset.value_cny, 0))}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[840px]">
                    <thead>
                      <tr className="text-[10px] text-muted-foreground border-b border-border/50">
                        <th className="text-left font-medium px-4 md:px-6 py-2.5">资产</th>
                        <th className="text-right font-medium px-3 py-2.5">数量</th>
                        <th className="text-right font-medium px-3 py-2.5">价格</th>
                        <th className="text-right font-medium px-3 py-2.5">汇率</th>
                        <th className="text-right font-medium px-3 py-2.5">人民币市值</th>
                        <th className="text-right font-medium px-3 py-2.5">敞口</th>
                        <th className="text-right font-medium px-4 md:px-6 py-2.5">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assets.map(asset => (
                        <tr key={asset.id} className="border-b border-border/40 last:border-0 hover:bg-accent/15">
                          <td className="px-4 md:px-6 py-3">
                            <div className="text-[13px] font-medium">{asset.name}</div>
                            <div className="text-[10px] text-muted-foreground mt-0.5">
                              {[asset.symbol, asset.account_name, sourceLabel(asset.source_system)]
                                .filter(Boolean)
                                .join(' · ')}
                            </div>
                          </td>
                          <td className="text-right px-3 py-3 text-[12px] tabular-nums">
                            {asset.valuation_method === 'manual'
                              ? '—'
                              : asset.quantity.toLocaleString('zh-CN')}
                          </td>
                          <td className="text-right px-3 py-3 text-[12px] tabular-nums">
                            {asset.current_price == null
                              ? '—'
                              : `${asset.currency} ${asset.current_price.toLocaleString('zh-CN')}`}
                          </td>
                          <td className="text-right px-3 py-3 text-[12px] tabular-nums">
                            {asset.currency === 'CNY' ? '1.0000' : asset.exchange_rate.toFixed(4)}
                          </td>
                          <td className={`text-right px-3 py-3 text-[13px] font-medium tabular-nums ${
                            asset.value_cny < 0 ? 'text-destructive' : ''
                          }`}>
                            {money(asset.value_cny)}
                          </td>
                          <td className="text-right px-3 py-3 text-[12px] text-muted-foreground tabular-nums">
                            {asset.category === 'future' || asset.category === 'option'
                              ? money(asset.exposure_cny)
                              : '—'}
                          </td>
                          <td className="text-right px-4 md:px-6 py-3">
                            <div className="inline-flex items-center gap-1">
                              <Button variant="ghost" size="icon" onClick={() => openEdit(asset)} title="编辑">
                                <Pencil className="w-3.5 h-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => removeAsset(asset)}
                                title="删除"
                              >
                                <Trash2 className="w-3.5 h-3.5 text-destructive" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingId ? '编辑资产' : '添加资产'}</DialogTitle>
            <DialogDescription>
              证券按数量 × 价格估值；现金、负债和账户权益可直接填写金额；期货同时记录保证金权益和名义敞口。
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label>资产类别</Label>
              <Select
                value={form.category}
                onValueChange={value => {
                  const category = value as AssetCategory
                  const derivative = category === 'future'
                  const manual = ['cash', 'liability', 'private_fund', 'adjustment'].includes(category)
                  setForm(current => ({
                    ...current,
                    category,
                    valuation_method: derivative ? 'derivative' : manual ? 'manual' : 'price',
                    currency:
                      category === 'b_stock'
                        ? 'USD'
                        : current.currency,
                  }))
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORY_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>账户</Label>
              <Input
                value={form.account_name}
                onChange={event => setForm(current => ({ ...current, account_name: event.target.value }))}
                placeholder="默认账户"
              />
            </div>
            <div>
              <Label>名称</Label>
              <Input
                value={form.name}
                onChange={event => setForm(current => ({ ...current, name: event.target.value }))}
                placeholder="例如：沪深300ETF"
              />
            </div>
            <div>
              <Label>代码 / 合约</Label>
              <Input
                value={form.symbol}
                onChange={event => setForm(current => ({ ...current, symbol: event.target.value }))}
                placeholder="510300 / IF2608"
              />
            </div>
            <div>
              <Label>估值方式</Label>
              <Select
                value={form.valuation_method}
                onValueChange={value =>
                  setForm(current => ({ ...current, valuation_method: value as ValuationMethod }))
                }
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="price">数量 × 价格</SelectItem>
                  <SelectItem value="manual">直接金额</SelectItem>
                  <SelectItem value="derivative">期货权益 + 名义敞口</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>市场</Label>
              <Input
                value={form.market}
                onChange={event => setForm(current => ({ ...current, market: event.target.value }))}
                placeholder="CN / HK / CFFEX"
              />
            </div>
            <div>
              <Label>币种</Label>
              <Select
                value={form.currency}
                onValueChange={value =>
                  setForm(current => ({
                    ...current,
                    currency: value as AssetPayload['currency'],
                    exchange_rate: value === 'CNY' ? 1 : current.exchange_rate,
                  }))
                }
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="CNY">人民币 CNY</SelectItem>
                  <SelectItem value="HKD">港币 HKD</SelectItem>
                  <SelectItem value="USD">美元 USD</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>兑人民币汇率</Label>
              <Input
                type="number"
                step="0.000001"
                min="0"
                value={form.exchange_rate}
                disabled={form.currency === 'CNY'}
                onChange={event =>
                  setForm(current => ({ ...current, exchange_rate: Number(event.target.value) || 1 }))
                }
              />
              {form.category === 'b_stock' && (
                <p className="text-[10px] text-muted-foreground mt-1.5">
                  沪B选择 USD，深B选择 HKD；市值会先按原币计算再折成人民币。
                </p>
              )}
            </div>
            {isPriceValuation && (
              <>
                <div>
                  <Label>数量 / 份额</Label>
                  <Input
                    type="number"
                    step="any"
                    value={form.quantity}
                    onChange={event =>
                      setForm(current => ({ ...current, quantity: Number(event.target.value) || 0 }))
                    }
                  />
                </div>
                <div>
                  <Label>当前价格 / 净值</Label>
                  <Input
                    type="number"
                    step="any"
                    value={form.current_price ?? ''}
                    onChange={event =>
                      setForm(current => ({
                        ...current,
                        current_price: toNullableNumber(event.target.value),
                      }))
                    }
                  />
                </div>
                <div>
                  <Label>成本价（可选）</Label>
                  <Input
                    type="number"
                    step="any"
                    value={form.cost_price ?? ''}
                    onChange={event =>
                      setForm(current => ({
                        ...current,
                        cost_price: toNullableNumber(event.target.value),
                      }))
                    }
                  />
                </div>
              </>
            )}
            {!isPriceValuation && (
              <div>
                <Label>{isDerivative ? '账户权益 / 保证金' : '金额'}</Label>
                <Input
                  type="number"
                  step="any"
                  value={isDerivative ? (form.margin ?? '') : (form.manual_amount ?? '')}
                  onChange={event => {
                    const value = toNullableNumber(event.target.value)
                    setForm(current =>
                      isDerivative
                        ? { ...current, margin: value }
                        : { ...current, manual_amount: value },
                    )
                  }}
                />
              </div>
            )}
            {isDerivative && (
              <>
                <div>
                  <Label>方向</Label>
                  <Select
                    value={form.position_side}
                    onValueChange={value =>
                      setForm(current => ({ ...current, position_side: value as PositionSide }))
                    }
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="long">多头</SelectItem>
                      <SelectItem value="short">空头</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>合约手数</Label>
                  <Input
                    type="number"
                    step="any"
                    value={form.quantity}
                    onChange={event =>
                      setForm(current => ({ ...current, quantity: Number(event.target.value) || 0 }))
                    }
                  />
                </div>
                <div>
                  <Label>合约价格</Label>
                  <Input
                    type="number"
                    step="any"
                    value={form.current_price ?? ''}
                    onChange={event =>
                      setForm(current => ({
                        ...current,
                        current_price: toNullableNumber(event.target.value),
                      }))
                    }
                  />
                </div>
                <div>
                  <Label>合约乘数</Label>
                  <Input
                    type="number"
                    step="any"
                    min="0"
                    value={form.contract_multiplier}
                    onChange={event =>
                      setForm(current => ({
                        ...current,
                        contract_multiplier: Number(event.target.value) || 1,
                      }))
                    }
                  />
                </div>
              </>
            )}
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button onClick={saveAsset} disabled={saving}>
              {saving ? '保存中…' : '保存'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
