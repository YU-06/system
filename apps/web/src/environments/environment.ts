import type { Environment } from '@abp/ng.core';

export const environment: Environment = {
  production: true,
  application: { name: 'BrainSeg' },
  apis: { default: { url: '', rootNamespace: 'BrainSeg' } },
};
