import { test, expect, type Page } from '@playwright/test'
import { generateUUID, giveConsent, setupApiMocks } from './utils'
import type { ChatResponseChunk, UncertaintyRead } from '../src/services/chat'

const BASE_URL = 'http://localhost:5173'

async function mockStreamingQuery(
  page: Page,
  uncertainty: UncertaintyRead | null,
  nonAnswer = false
) {
  // Registered after setupApiMocks, so it takes precedence over the default /api/query mock.
  await page.route('*/**/api/query', async (route) => {
    const now = new Date().toISOString()
    const chunks: Array<ChatResponseChunk> = [
      { content: 'The application deadline is July 15.' },
      { non_answer: nonAnswer }
    ]
    if (uncertainty) {
      chunks.push({ uncertainty })
    }
    chunks.push({
      conversation_id: generateUUID(),
      user_message: { id: 0, role: 'user', content: 'Deadline?', created_at: now, sources: [] },
      assistant_message: {
        id: 1,
        role: 'assistant',
        content: 'The application deadline is July 15.',
        non_answer: nonAnswer,
        created_at: now,
        sources: [],
        uncertainty
      }
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: chunks.map((chunk) => JSON.stringify(chunk)).join('\n') + '\n'
    })
  })
}

async function ask(page: Page) {
  await page.locator('textarea#message-input').fill('When is the application deadline?')
  await page.locator('#send-message-button').click()
  await expect(page.locator('div.message').nth(1)).toContainText('July 15')
}

function uncertainty(flagged: boolean): UncertaintyRead {
  return {
    method: 'kle-heat',
    entropy: flagged ? 1.1 : 0.05,
    normalized_entropy: flagged ? 0.68 : 0.03,
    flagged,
    num_samples: 5
  }
}

test.describe('Hallucination warning', () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page)
    await page.goto(BASE_URL)
    await giveConsent(page)
  })

  test('shows a warning for a flagged answer', async ({ page }) => {
    await mockStreamingQuery(page, uncertainty(true))
    await ask(page)
    await expect(page.getByTestId('uncertaintyWarning')).toBeVisible()
    await expect(page.getByTestId('uncertaintyWarning')).toContainText('may be unreliable')
    // Score details are for the admin view only
    await expect(page.getByTestId('uncertaintyDetails')).toHaveCount(0)
  })

  test('shows no warning for a consistent answer', async ({ page }) => {
    await mockStreamingQuery(page, uncertainty(false))
    await ask(page)
    await expect(page.getByTestId('uncertaintyWarning')).toHaveCount(0)
  })

  test('shows no warning when no score was computed', async ({ page }) => {
    await mockStreamingQuery(page, null)
    await ask(page)
    await expect(page.getByTestId('uncertaintyWarning')).toHaveCount(0)
  })

  test('shows no warning when CIRA declined to answer', async ({ page }) => {
    await mockStreamingQuery(page, uncertainty(true), true)
    await ask(page)
    await expect(page.getByTestId('uncertaintyWarning')).toHaveCount(0)
  })
})
