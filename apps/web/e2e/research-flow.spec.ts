import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';

function createNifti(): Buffer {
  const buffer = Buffer.alloc(480);
  buffer.writeInt32LE(348, 0);
  buffer.writeInt16LE(3, 40);
  buffer.writeInt16LE(4, 42);
  buffer.writeInt16LE(4, 44);
  buffer.writeInt16LE(2, 46);
  buffer.writeInt16LE(16, 70);
  buffer.writeInt16LE(32, 72);
  buffer.writeFloatLE(1, 76);
  buffer.writeFloatLE(1, 80);
  buffer.writeFloatLE(1, 84);
  buffer.writeFloatLE(1, 88);
  buffer.writeFloatLE(352, 108);
  buffer.writeInt16LE(1, 254);
  buffer.writeFloatLE(1, 280);
  buffer.writeFloatLE(1, 300);
  buffer.writeFloatLE(1, 320);
  buffer.write('n+1\0', 344, 'binary');
  for (let index = 0; index < 32; index += 1) {
    buffer.writeFloatLE(index % 2, 352 + index * 4);
  }
  return buffer;
}

test('uploads a NIfTI, waits for its job, and opens a result using API fixtures', async ({
  page,
}) => {
  const nifti = createNifti();
  const sha256 = createHash('sha256').update(nifti).digest('hex');
  let jobReads = 0;
  const grants = {
    'BrainSeg.BrainStudies': true,
    'BrainSeg.BrainStudies.Create': true,
    'BrainSeg.BrainStudies.RegisterGroundTruth': true,
    'BrainSeg.SegmentationJobs': true,
    'BrainSeg.SegmentationJobs.Create': true,
    'BrainSeg.SegmentationJobs.Cancel': true,
    'BrainSeg.SegmentationJobs.Retry': true,
    'BrainSeg.ModelVersions': true,
    'BrainSeg.SegmentationResults': true,
    'BrainSeg.SegmentationResults.Download': true,
    'BrainSeg.SegmentationResults.Evaluate': true,
    'BrainSeg.ExperimentRuns': true,
  };
  await page.route('**/api/abp/application-configuration**', async (route) => {
    await route.fulfill({ json: { auth: { grantedPolicies: grants } } });
  });
  await page.route('**/api/app/**', async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (pathname === '/api/app/brain-study' && request.method() === 'GET') {
      await route.fulfill({ json: { items: [], totalCount: 0 } });
    } else if (pathname === '/api/app/model-version' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          items: [
            {
              id: 'model-1',
              name: 'U-Net fixture',
              architecture: 'UNet',
              semanticVersion: '1.0.0-test',
              preprocessingVersion: 'flair-v1',
              inputSize: 256,
              threshold: 0.5,
              isActive: true,
            },
          ],
          totalCount: 1,
        },
      });
    } else if (pathname === '/api/app/brain-study/upload' && request.method() === 'POST') {
      await route.fulfill({
        json: {
          id: 'study-1',
          studyNumber: 'S-001',
          pseudonym: 'anon-001',
          modality: 'T2-FLAIR',
          originalFileSha256: sha256,
          width: 4,
          height: 4,
          hasGroundTruth: false,
        },
      });
    } else if (pathname === '/api/app/segmentation-job' && request.method() === 'POST') {
      await route.fulfill({ json: { id: 'job-1', status: 'Pending', progress: 0 } });
    } else if (pathname === '/api/app/segmentation-job/job-1' && request.method() === 'GET') {
      jobReads += 1;
      const succeeded = jobReads > 1;
      await route.fulfill({
        json: {
          id: 'job-1',
          studyId: 'study-1',
          modelVersionId: 'model-1',
          modelSemanticVersion: '1.0.0-test',
          preprocessingVersion: 'flair-v1',
          status: succeeded ? 'Succeeded' : 'Pending',
          progress: succeeded ? 100 : 0,
          requestedTime: '2026-01-01T00:00:00Z',
          completedTime: succeeded ? '2026-01-01T00:00:02Z' : null,
        },
      });
    } else if (pathname === '/api/app/segmentation-result' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          items: [{ id: 'result-1', jobId: 'job-1' }],
          totalCount: 1,
        },
      });
    } else if (pathname === '/api/app/segmentation-result/result-1' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          id: 'result-1',
          jobId: 'job-1',
          groundTruthSha256: null,
          evaluationProtocol: null,
          dice: null,
          ioU: null,
          precision: null,
          recall: null,
          inferenceMilliseconds: 12,
          preprocessingMilliseconds: 2,
          postprocessingMilliseconds: 1,
        },
      });
    } else if (
      pathname === '/api/app/segmentation-result/result-1/download-mask' &&
      request.method() === 'POST'
    ) {
      await route.fulfill({
        body: nifti,
        headers: { 'content-type': 'application/octet-stream' },
      });
    } else if (pathname === '/api/app/brain-study/study-1' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          id: 'study-1',
          pseudonym: 'anon-001',
          width: 4,
          height: 4,
          hasGroundTruth: false,
        },
      });
    } else {
      await route.fulfill({ status: 404, json: { error: { code: 'FIXTURE_NOT_FOUND' } } });
    }
  });

  await page.goto('/studies');
  await expect(page.getByRole('heading', { name: '病例管理' })).toBeVisible();
  await page.getByLabel('研究编号', { exact: true }).fill('S-001');
  await page.getByLabel('匿名编号', { exact: true }).fill('anon-001');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'study.nii',
    mimeType: 'application/octet-stream',
    buffer: nifti,
  });
  await expect(page.getByText(/浏览器初步校验通过/)).toBeVisible();
  await page.getByRole('button', { name: '上传病例' }).click();
  await expect(
    page.locator('.success-note').filter({ hasText: '服务器 SHA-256' }).getByText(sha256),
  ).toBeVisible();
  await page.getByLabel('模型版本').selectOption('model-1');
  await page.getByRole('button', { name: '创建分割任务' }).click();

  await expect(page.getByRole('heading', { name: '任务详情' })).toBeVisible();
  await expect(page.getByRole('link', { name: '打开分割结果' })).toBeVisible({ timeout: 8000 });
  await page.getByRole('link', { name: '打开分割结果' }).click();
  await expect(page.getByRole('heading', { name: '逐层结果查看' })).toBeVisible();
  await expect(page.getByText('未提供可评价的真实标签。')).toBeVisible();
  await expect(page.getByText('1.0.0-test')).toBeVisible();
});
