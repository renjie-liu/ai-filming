import { useCallback, useRef, useState } from 'react'
import { toChineseErrorMessage } from '../../../utils/errorMessage'

export type GenerationDraftState =
  | 'idle'
  | 'draft_changed'
  | 'context_changed'
  | 'deriving'
  | 'derived'
  | 'submitting'
  | 'submitted'
  | 'error'

type Updater<T> = T | ((prev: T) => T)

export type UseGenerationDraftOptions<TBase, TContext, TDerived, TSubmitResult> = {
  initialBase: TBase
  initialContext: TContext
  derive: (args: { base: TBase; context: TContext }) => Promise<TDerived>
  submit?: (args: { base: TBase; context: TContext; derived: TDerived }) => Promise<TSubmitResult>
}

export type UseGenerationDraftResult<TBase, TContext, TDerived, TSubmitResult> = {
  base: TBase
  context: TContext
  derived: TDerived | null
  state: GenerationDraftState
  error: string | null
  lastDerivedAt: number | null
  setBase: (updater: Updater<TBase>) => void
  setContext: (updater: Updater<TContext>) => void
  replaceBase: (next: TBase) => void
  replaceContext: (next: TContext) => void
  setDerived: (next: TDerived | null) => void
  setState: (next: GenerationDraftState) => void
  hydrate: (args: {
    base: TBase
    context: TContext
    derived?: TDerived | null
    state?: GenerationDraftState
  }) => void
  deriveNow: (overrides?: { base?: TBase; context?: TContext }) => Promise<TDerived | null>
  submitNow: () => Promise<TSubmitResult | null>
  /**
   * 最近一次 deriveNow / submitNow 失败的中文原因（同步读取）。
   * 为什么存在：两者失败时返回 null，而 `error` 状态要到下一次渲染才更新；
   * 调用方需要在同一个事件处理中把真实原因（如后端返回的 404/400 说明）提示给用户。
   */
  getLastError: () => string | null
  resetDerived: () => void
}

function applyUpdater<T>(prev: T, updater: Updater<T>): T {
  return typeof updater === 'function' ? (updater as (value: T) => T)(prev) : updater
}

export function useGenerationDraft<TBase, TContext, TDerived, TSubmitResult = void>(
  options: UseGenerationDraftOptions<TBase, TContext, TDerived, TSubmitResult>,
): UseGenerationDraftResult<TBase, TContext, TDerived, TSubmitResult> {
  const { initialBase, initialContext, derive, submit } = options
  const [base, setBaseState] = useState<TBase>(initialBase)
  const [context, setContextState] = useState<TContext>(initialContext)
  const [derived, setDerivedState] = useState<TDerived | null>(null)
  const [state, setState] = useState<GenerationDraftState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [lastDerivedAt, setLastDerivedAt] = useState<number | null>(null)
  // 与 error 状态同步写入，供调用方在同一次事件处理中读取失败原因。
  const lastErrorRef = useRef<string | null>(null)

  const setBase = useCallback((updater: Updater<TBase>) => {
    setBaseState((prev) => applyUpdater(prev, updater))
    setState((prev) => (prev === 'idle' ? 'draft_changed' : 'draft_changed'))
    setError(null)
  }, [])

  const setContext = useCallback((updater: Updater<TContext>) => {
    setContextState((prev) => applyUpdater(prev, updater))
    setState((prev) => (prev === 'idle' ? 'context_changed' : 'context_changed'))
    setError(null)
  }, [])

  const replaceBase = useCallback((next: TBase) => {
    setBaseState(next)
    setError(null)
  }, [])

  const replaceContext = useCallback((next: TContext) => {
    setContextState(next)
    setError(null)
  }, [])

  const setDerived = useCallback((next: TDerived | null) => {
    setDerivedState(next)
    if (next === null) {
      setLastDerivedAt(null)
    }
  }, [])

  const resetDerived = useCallback(() => {
    setDerivedState(null)
    setLastDerivedAt(null)
    setError(null)
    setState('idle')
  }, [])

  const hydrate = useCallback((args: {
    base: TBase
    context: TContext
    derived?: TDerived | null
    state?: GenerationDraftState
  }) => {
    const nextDerived = args.derived ?? null
    setBaseState(args.base)
    setContextState(args.context)
    setDerivedState(nextDerived)
    setLastDerivedAt(nextDerived ? Date.now() : null)
    setError(null)
    setState(args.state ?? (nextDerived ? 'derived' : 'idle'))
  }, [])

  const deriveNow = useCallback(async (overrides?: { base?: TBase; context?: TContext }) => {
    const nextBase = overrides?.base ?? base
    const nextContext = overrides?.context ?? context
    setState('deriving')
    setError(null)
    lastErrorRef.current = null
    try {
      const next = await derive({ base: nextBase, context: nextContext })
      setDerivedState(next)
      setLastDerivedAt(Date.now())
      setState('derived')
      return next
    } catch (err) {
      const reason = toChineseErrorMessage(err, '提示词生成失败，请稍后重试')
      lastErrorRef.current = reason
      setState('error')
      setError(reason)
      return null
    }
  }, [base, context, derive])

  const submitNow = useCallback(async () => {
    if (!submit) return null
    let nextDerived = derived
    const needsDerive =
      !nextDerived ||
      (state !== 'derived' && state !== 'submitted')
    if (needsDerive) {
      nextDerived = await deriveNow()
      if (!nextDerived) return null
    }
    const stableDerived = nextDerived as TDerived
    setState('submitting')
    setError(null)
    lastErrorRef.current = null
    try {
      const result = await submit({ base, context, derived: stableDerived })
      setState('submitted')
      return result
    } catch (err) {
      const reason = toChineseErrorMessage(err, '提交失败，请稍后重试')
      lastErrorRef.current = reason
      setState('error')
      setError(reason)
      return null
    }
  }, [base, context, deriveNow, derived, submit])

  const getLastError = useCallback(() => lastErrorRef.current, [])

  return {
    base,
    context,
    derived,
    state,
    error,
    lastDerivedAt,
    setBase,
    setContext,
    replaceBase,
    replaceContext,
    setDerived,
    setState,
    hydrate,
    deriveNow,
    submitNow,
    getLastError,
    resetDerived,
  }
}
