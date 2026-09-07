import { expect, it } from 'bun:test'
import { budgetFailures } from '../../../scripts/check-bundle-budget.mjs'

it('fails each exceeded startup budget rather than just warning', () => {
  expect(budgetFailures({ eagerBytes: 101, eagerGzipBytes: 21, largestChunkBytes: 51 },
    { eagerBytes: 100, eagerGzipBytes: 20, largestChunkBytes: 50 })).toHaveLength(3)
})

it('accepts values at the budget boundary', () => {
  expect(budgetFailures({ eagerBytes: 100 }, { eagerBytes: 100 })).toEqual([])
})
