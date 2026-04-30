// Type declarations for bun:test module
declare module "bun:test" {
  export function describe(label: string, fn: () => void): void
  export function it(label: string, fn: () => void | Promise<void>): void
  export function test(label: string, fn: () => void | Promise<void>): void
  export function beforeEach(fn: () => void | Promise<void>): void
  export function afterEach(fn: () => void | Promise<void>): void
  export function beforeAll(fn: () => void | Promise<void>): void
  export function afterAll(fn: () => void | Promise<void>): void
  export function mock<T extends (...args: unknown[]) => unknown>(fn?: T): T & { mock: { calls: unknown[][] } }
  export const spyOn: typeof jest.spyOn

  interface Expect {
    (value: unknown): jest.Matchers<unknown>
    /** Fail the test immediately with a message. Use inside a try block to assert an unreachable code path. */
    unreachable(message?: string): never
    /** Assert that a value matches an asymmetric matcher. */
    assertions(count: number): void
    /** Assert that a specific number of assertions were called. */
    hasAssertions(): void
    any(constructor: unknown): unknown
    anything(): unknown
    arrayContaining(arr: unknown[]): unknown
    objectContaining(obj: Record<string, unknown>): unknown
    stringContaining(str: string): unknown
    stringMatching(pattern: string | RegExp): unknown
  }

  export const expect: Expect
}
