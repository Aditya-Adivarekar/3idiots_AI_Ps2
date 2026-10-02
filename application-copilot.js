(function (root, factory) {
  const createService = factory();
  if (typeof module === 'object' && module.exports) module.exports = createService;
  else root.ApplicationCopilot = createService(root.localStorage);
})(typeof window === 'undefined' ? globalThis : window, function () {
  'use strict';

  const STORAGE_KEY = 'ys-applications';
  const DOCUMENTS = Object.freeze({
    income_certificate: { label: 'Income certificate', aliases: ['income certificate', 'family income certificate', 'income proof'] },
    domicile_proof: { label: 'Domicile or residence proof', aliases: ['domicile certificate', 'domicile proof', 'residence certificate', 'residence proof', 'address proof'] },
    caste_certificate: { label: 'Caste or category certificate', aliases: ['caste certificate', 'category certificate', 'sc certificate', 'st certificate', 'obc certificate', 'scheduled caste certificate', 'scheduled tribe certificate'] },
    marksheet: { label: 'Marksheet or transcript', aliases: ['marksheet', 'mark sheet', 'transcript', 'academic record'] },
    bank_passbook: { label: 'Bank passbook or account proof', aliases: ['bank passbook', 'passbook', 'bank account proof', 'bank statement'] },
    identity_proof: { label: 'Identity proof', aliases: ['identity proof', 'identity card', 'aadhaar', 'aadhar', 'voter id', 'pan card'] },
    admission_proof: { label: 'Admission proof', aliases: ['admission proof', 'admission letter', 'enrolment proof', 'enrollment proof'] },
    bonafide_certificate: { label: 'Bonafide certificate', aliases: ['bonafide certificate', 'bona fide certificate', 'bonafide'] },
    fee_receipt: { label: 'Fee receipt', aliases: ['fee receipt', 'tuition receipt', 'fee proof'] }
  });
  const STAGES = new Set(['shortlisted', 'preparing', 'submitted']);

  function createService(storage) {
    if (!storage) throw new TypeError('A storage implementation is required');

    function load() {
      try {
        const value = JSON.parse(storage.getItem(STORAGE_KEY) || '{}');
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
      } catch (_) {
        return {};
      }
    }

    function persist(applications) {
      storage.setItem(STORAGE_KEY, JSON.stringify(applications));
      return applications;
    }

    function trackScheme(scheme) {
      const id = String(scheme.id || scheme.schemeId || '');
      if (!id) throw new Error('A scheme id is required');
      const applications = load();
      const current = applications[id] || {};
      applications[id] = {
        schemeId: id,
        title: scheme.name || scheme.title || current.title || 'Scholarship scheme',
        source: scheme.source || current.source || '',
        sourceUrl: scheme.url || scheme.sourceUrl || current.sourceUrl || '',
        requiredDocuments: current.requiredDocuments || [],
        uploadedFiles: current.uploadedFiles || [],
        deadline: current.deadline || '',
        deadlineReviewed: current.deadlineReviewed || false,
        noDeadline: current.noDeadline || false,
        stage: current.stage || 'shortlisted',
        updatedAt: new Date().toISOString()
      };
      persist(applications);
      return clone(applications[id]);
    }

    function update(schemeId, changes) {
      const applications = load();
      if (!applications[schemeId]) throw new Error(`Scheme is not tracked: ${schemeId}`);
      const current = applications[schemeId];
      const next = { ...current, ...changes, schemeId, updatedAt: new Date().toISOString() };
      if (changes.stage && !STAGES.has(changes.stage)) throw new Error(`Unsupported application stage: ${changes.stage}`);
      if (next.deadline && !/^\d{4}-\d{2}-\d{2}$/.test(next.deadline)) throw new Error('Deadline must be an ISO date');
      applications[schemeId] = next;
      persist(applications);
      return clone(next);
    }

    function addRequiredDocument(schemeId, documentType) {
      if (!DOCUMENTS[documentType]) throw new Error(`Unsupported document type: ${documentType}`);
      const application = get(schemeId);
      if (!application) throw new Error(`Scheme is not tracked: ${schemeId}`);
      if (application.requiredDocuments.includes(documentType)) return application;
      return update(schemeId, { requiredDocuments: [...application.requiredDocuments, documentType] });
    }

    function removeRequiredDocument(schemeId, documentType) {
      const application = get(schemeId);
      if (!application) return null;
      return update(schemeId, { requiredDocuments: application.requiredDocuments.filter(item => item !== documentType) });
    }

    function addFiles(schemeId, files) {
      const application = get(schemeId);
      if (!application) throw new Error(`Scheme is not tracked: ${schemeId}`);
      const existing = new Map(application.uploadedFiles.map(file => [file.name.toLowerCase(), file]));
      Array.from(files || []).forEach(file => {
        const name = String(file.name || file.filename || '').split(/[\\/]/).pop().trim();
        if (!name) return;
        existing.set(name.toLowerCase(), {
          name,
          documentType: classifyDocument(name),
          size: Number(file.size) || 0,
          addedAt: new Date().toISOString()
        });
      });
      return update(schemeId, { uploadedFiles: [...existing.values()] });
    }

    function removeFile(schemeId, filename) {
      const application = get(schemeId);
      if (!application) return null;
      return update(schemeId, {
        uploadedFiles: application.uploadedFiles.filter(file => file.name !== filename)
      });
    }

    function get(schemeId) {
      const application = load()[schemeId];
      return application ? clone(application) : null;
    }

    function list(schemeIds) {
      const applications = load();
      return (schemeIds || Object.keys(applications))
        .map(id => applications[id])
        .filter(Boolean)
        .map(clone);
    }

    function readiness(schemeId) {
      const application = get(schemeId);
      if (!application) return null;
      const checklist = application.requiredDocuments.map(documentType => {
        const definition = DOCUMENTS[documentType];
        const matchingFiles = application.uploadedFiles
          .filter(file => file.documentType === documentType || classifyDocument(file.name) === documentType)
          .map(file => file.name);
        return {
          documentType,
          label: definition.label,
          status: matchingFiles.length ? 'present' : 'missing',
          matchingFiles
        };
      });
      const missing = checklist.filter(item => item.status === 'missing');
      const requirementsConfigured = checklist.length > 0;
      const deadlineReviewed = Boolean(application.deadlineReviewed || application.noDeadline);
      const ready = requirementsConfigured && missing.length === 0 && deadlineReviewed;
      return {
        schemeId,
        status: ready ? 'ready_to_apply' : application.stage === 'submitted' ? 'submitted' : 'preparing',
        ready,
        requirementsConfigured,
        deadlineReviewed,
        checklist,
        missingDocuments: missing.map(item => item.documentType),
        nextStep: !requirementsConfigured
          ? 'Review the official requirements and add the required documents.'
          : missing.length
            ? `Add ${missing[0].label.toLowerCase()}.`
            : !deadlineReviewed
              ? 'Confirm the deadline on the official source, or record that none is published.'
              : 'Your checklist is ready for your final review.'
      };
    }

    return Object.freeze({
      storageKey: STORAGE_KEY,
      documentTypes: DOCUMENTS,
      load,
      trackScheme,
      update,
      addRequiredDocument,
      removeRequiredDocument,
      addFiles,
      removeFile,
      get,
      list,
      readiness
    });
  }

  function classifyDocument(filename) {
    const normalized = String(filename || '').toLowerCase().replace(/\.[a-z0-9]{1,8}$/, '').replace(/[^a-z0-9]+/g, ' ').trim();
    for (const [documentType, definition] of Object.entries(DOCUMENTS)) {
      if (definition.aliases.some(alias => normalized.includes(alias))) return documentType;
    }
    return '';
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  return createService;
});
