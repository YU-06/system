import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import prettier from 'prettier';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const envPath = path.resolve(root, '../../.env');
if (existsSync(envPath)) process.loadEnvFile(envPath);
const generation = spawnSync(
  process.execPath,
  [
    path.join(root, 'node_modules/@angular/cli/bin/ng.js'),
    'generate',
    '@abp/ng.schematics:proxy-add',
    '--module',
    'app',
    '--api-name',
    'default',
    '--target',
    'brainseg',
    '--source',
    'brainseg',
    '--url',
    process.env.BACKEND_DEV_URL || 'http://127.0.0.1:5000',
    '--service-type',
    'application',
    '--interactive=false',
    ...process.argv.slice(2),
  ],
  { cwd: root, stdio: 'inherit' },
);
if (generation.status !== 0) process.exit(generation.status ?? 1);

const proxyRoot = path.join(root, 'src/app/proxy');
for (const relativePath of readdirSync(proxyRoot, { recursive: true })) {
  if (!relativePath.endsWith('.ts')) continue;
  const filePath = path.join(proxyRoot, relativePath);
  const source = ts.createSourceFile(
    filePath,
    readFileSync(filePath, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
  );
  const transformed = ts.transform(source, [
    (context) => {
      const visit = (node) =>
        node.kind === ts.SyntaxKind.AnyKeyword
          ? context.factory.createKeywordTypeNode(ts.SyntaxKind.UnknownKeyword)
          : ts.visitEachChild(node, visit, context);
      return (node) => ts.visitNode(node, visit);
    },
  ]);
  const content = ts
    .createPrinter({ newLine: ts.NewLineKind.LineFeed })
    .printFile(transformed.transformed[0]);
  const options = await prettier.resolveConfig(filePath);
  writeFileSync(filePath, await prettier.format(content, { ...options, filepath: filePath }));
  transformed.dispose();
}

const readmePath = path.join(proxyRoot, 'README.md');
const disclaimer = 'Research and teaching only. Not a medical device. Not for clinical diagnosis.';
const readme = readFileSync(readmePath, 'utf8');
if (!readme.includes(disclaimer)) writeFileSync(readmePath, `${disclaimer}\n\n${readme}`);
