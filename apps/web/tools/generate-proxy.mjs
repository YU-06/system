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
  const withUploadProgress = ts.transform(transformed.transformed[0], [
    (context) => {
      const factory = context.factory;
      const visitUploadRequest = (node) => {
        if (
          ts.isCallExpression(node) &&
          ts.isPropertyAccessExpression(node.expression) &&
          node.expression.name.text === 'request' &&
          node.arguments.length > 0 &&
          ts.isObjectLiteralExpression(node.arguments[0]) &&
          !node.arguments[0].properties.some(
            (property) =>
              ts.isPropertyAssignment(property) && property.name.getText(source) === 'reportProgress',
          )
        ) {
          const request = node.arguments[0];
          const updatedRequest = factory.updateObjectLiteralExpression(request, [
            ...request.properties,
            factory.createPropertyAssignment(
              'reportProgress',
              factory.createPropertyAccessChain(
                factory.createIdentifier('config'),
                factory.createToken(ts.SyntaxKind.QuestionDotToken),
                'reportProgress',
              ),
            ),
          ]);
          return factory.updateCallExpression(node, node.expression, node.typeArguments, [
            updatedRequest,
            ...node.arguments.slice(1),
          ]);
        }
        return ts.visitEachChild(node, visitUploadRequest, context);
      };
      const visit = (node) => {
        if (
          ts.isPropertyDeclaration(node) &&
          node.initializer &&
          ts.isArrowFunction(node.initializer) &&
          node.initializer.parameters.some(
            (parameter) =>
              parameter.type &&
              ts.isTypeReferenceNode(parameter.type) &&
              parameter.type.typeName.getText(source) === 'FormData',
          )
        ) {
          const arrow = node.initializer;
          const parameters = arrow.parameters.map((parameter) => {
            if (
              ts.isIdentifier(parameter.name) &&
              parameter.name.text === 'config' &&
              parameter.type
            ) {
              const progressProperty = factory.createPropertySignature(
                undefined,
                'reportProgress',
                factory.createToken(ts.SyntaxKind.QuestionToken),
                factory.createKeywordTypeNode(ts.SyntaxKind.BooleanKeyword),
              );
              return factory.updateParameterDeclaration(
                parameter,
                parameter.modifiers,
                parameter.dotDotDotToken,
                parameter.name,
                parameter.questionToken,
                factory.createIntersectionTypeNode([
                  parameter.type,
                  factory.createTypeLiteralNode([progressProperty]),
                ]),
                parameter.initializer,
              );
            }
            return parameter;
          });
          const body = ts.visitNode(arrow.body, visitUploadRequest);
          const updatedArrow = factory.updateArrowFunction(
            arrow,
            arrow.modifiers,
            arrow.typeParameters,
            parameters,
            arrow.type,
            arrow.equalsGreaterThanToken,
            body,
          );
          return factory.updatePropertyDeclaration(
            node,
            node.modifiers,
            node.name,
            node.questionToken ?? node.exclamationToken,
            node.type,
            updatedArrow,
          );
        }
        return ts.visitEachChild(node, visit, context);
      };
      return (node) => ts.visitNode(node, visit);
    },
  ]);
  let content = ts
    .createPrinter({ newLine: ts.NewLineKind.LineFeed })
    .printFile(withUploadProgress.transformed[0]);
  if (filePath.endsWith(path.join('research', 'brain-study.service.ts'))) {
    content = content
      .replace(/^\s+UploadBrainStudyInput,\r?\n/gm, '')
      .replace(/^\s+UploadGroundTruthInput,\r?\n/gm, '');
  }
  const options = await prettier.resolveConfig(filePath);
  writeFileSync(filePath, await prettier.format(content, { ...options, filepath: filePath }));
  withUploadProgress.dispose();
  transformed.dispose();
}

const readmePath = path.join(proxyRoot, 'README.md');
const disclaimer = 'Research and teaching only. Not a medical device. Not for clinical diagnosis.';
const readme = readFileSync(readmePath, 'utf8');
if (!readme.includes(disclaimer)) writeFileSync(readmePath, `${disclaimer}\n\n${readme}`);
