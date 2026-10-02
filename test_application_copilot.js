const test = require('node:test');
const assert = require('node:assert/strict');
const createApplicationCopilot = require('../application-copilot.js');

function createStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value)
  };
}

test('shortlisted scheme becomes a durable copilot application', () => {
  const copilot = createApplicationCopilot(createStorage());
  const tracked = copilot.trackScheme({
    id: 'scheme-a',
    name: 'Income support',
    url: 'https://official.gov.in/scheme-a'
  });

  assert.equal(tracked.stage, 'shortlisted');
  assert.equal(copilot.get('scheme-a').sourceUrl, 'https://official.gov.in/scheme-a');
});

test('readiness combines scheme requirements, matched filenames, and deadline review', () => {
  const copilot = createApplicationCopilot(createStorage());
  copilot.trackScheme({ id: 'scheme-b', name: 'Merit support' });
  copilot.addRequiredDocument('scheme-b', 'marksheet');
  copilot.addRequiredDocument('scheme-b', 'domicile_proof');
  copilot.addFiles('scheme-b', [
    { name: 'Class12-transcript.pdf', size: 1200 },
    { name: 'residence-proof.jpg', size: 900 }
  ]);

  let result = copilot.readiness('scheme-b');
  assert.equal(result.ready, false);
  assert.equal(result.requirementsConfigured, true);
  assert.equal(result.deadlineReviewed, false);

  copilot.update('scheme-b', { deadline: '2026-10-31', deadlineReviewed: true });
  result = copilot.readiness('scheme-b');
  assert.equal(result.ready, true);
  assert.equal(result.status, 'ready_to_apply');
  assert.deepEqual(result.missingDocuments, []);
});

test('no configured checklist is never reported ready', () => {
  const copilot = createApplicationCopilot(createStorage());
  copilot.trackScheme({ id: 'scheme-c' });
  copilot.update('scheme-c', { noDeadline: true });

  const result = copilot.readiness('scheme-c');
  assert.equal(result.requirementsConfigured, false);
  assert.equal(result.ready, false);
  assert.match(result.nextStep, /official requirements/i);
});
