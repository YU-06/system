import { expect, test } from '@playwright/test';

test('status refresh, errors, research disclaimer, and responsive layout', async ({
  page,
}, testInfo) => {
  const unexpectedErrors: string[] = [];
  page.on('pageerror', (error) => unexpectedErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const expectedUnavailable =
      message.text().startsWith('Failed to load resource:') && message.text().includes('503');
    if (!expectedUnavailable) unexpectedErrors.push(message.text());
  });
  let unavailable = false;
  await page.route('**/api/app/system', async (route) => {
    await route.fulfill(
      unavailable
        ? {
            status: 503,
            headers: { 'X-Correlation-Id': 'e2e-research-123' },
            json: { error: { code: 'UNAVAILABLE' } },
          }
        : {
            json: {
              service: 'brainseg-backend',
              status: 'ok',
              dataset: 'BraTS 2020',
              modality: 'T2-FLAIR',
              serverTimeUtc: '2026-11-06T00:00:00Z',
            },
          },
    );
  });
  await page.goto('/');
  await expect(page).toHaveTitle('BrainSeg');
  await expect(page.getByRole('heading', { name: '系统概览' })).toBeVisible();
  await expect(page.getByTestId('connection-status')).toHaveText('已连接');
  await expect(page.getByRole('note')).toContainText('不用于临床诊断');
  await expect(page.getByText('暂无已执行实验')).toBeVisible();
  unavailable = true;
  await page.getByRole('button', { name: '刷新状态' }).click();
  await expect(page.getByRole('alert')).toHaveText('服务连接失败');
  await expect(page.getByText('e2e-research-123')).toBeVisible();
  unavailable = false;
  await page.getByRole('button', { name: '刷新状态' }).click();
  await expect(page.getByTestId('connection-status')).toHaveText('已连接');
  if (testInfo.project.name === 'mobile') {
    await page.setViewportSize({ width: 312, height: 844 });
    await expect(page.locator('.status-icon').first()).not.toBeVisible();
  }
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    imageReady: [...document.images].every((image) => image.complete && image.naturalWidth > 0),
  }));
  expect(layout.content).toBeLessThanOrEqual(layout.viewport);
  expect(layout.imageReady).toBe(true);
  expect(unexpectedErrors).toEqual([]);
});
