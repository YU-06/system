const fs = require('node:fs');
const path = require('node:path');

const envPath = path.resolve(__dirname, '../../.env');
if (fs.existsSync(envPath)) {
  process.loadEnvFile(envPath);
}
const target = process.env.BACKEND_DEV_URL || 'http://127.0.0.1:5000';
module.exports = {
  '/api': { target, secure: false },
  '/swagger': { target, secure: false },
  '/backend-health': { target, secure: false, pathRewrite: { '^/backend-health': '/health' } },
};
