import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_UPLOAD_BYTES,
  getCollectionReadiness,
  getUploadErrorMessage,
  getUploadOutcome,
  getUploadReadiness,
  isSupportedFile,
  isWithinUploadSizeLimit,
  isValidUuid,
} from "../src/lib/upload-workflow.ts";

const tenantCollectionId = "b387043b-9b5c-48db-a7b5-02d1a10f8411";

const readyInput = {
  collectionsState: "ready",
  collectionCount: 1,
  collectionId: tenantCollectionId,
  fileCount: 1,
  isUploading: false,
};

test("no collection selected blocks upload", () => {
  const readiness = getUploadReadiness({
    ...readyInput,
    collectionId: "",
  });

  assert.equal(readiness.ready, false);
  assert.equal(readiness.code, "missing");
  assert.match(readiness.message, /select a collection/i);
});

test("collections still loading blocks upload", () => {
  const readiness = getUploadReadiness({
    ...readyInput,
    collectionsState: "loading",
    collectionCount: 0,
    collectionId: "",
  });

  assert.equal(readiness.ready, false);
  assert.equal(readiness.code, "loading");
  assert.match(readiness.message, /loading collections/i);
});

test("empty collection list blocks upload", () => {
  const readiness = getUploadReadiness({
    ...readyInput,
    collectionCount: 0,
    collectionId: "",
  });

  assert.equal(readiness.ready, false);
  assert.equal(readiness.code, "empty");
  assert.match(readiness.message, /no collections/i);
});

test("invalid collection ID blocks upload", () => {
  const readiness = getUploadReadiness({
    ...readyInput,
    collectionId: "col_hr",
  });

  assert.equal(isValidUuid("col_hr"), false);
  assert.equal(readiness.ready, false);
  assert.equal(readiness.code, "invalid");
  assert.match(readiness.message, /invalid/i);
});

test("valid collection and file allow upload", () => {
  const readiness = getUploadReadiness(readyInput);

  assert.equal(isValidUuid(tenantCollectionId), true);
  assert.equal(readiness.ready, true);
  assert.equal(readiness.code, "ready");
  assert.equal(readiness.message, null);
});

test("missing or in-progress files block upload", () => {
  const noFiles = getUploadReadiness({ ...readyInput, fileCount: 0 });
  const inProgress = getUploadReadiness({ ...readyInput, isUploading: true });

  assert.equal(noFiles.ready, false);
  assert.equal(noFiles.code, "no-files");
  assert.match(noFiles.message, /select at least one file/i);

  assert.equal(inProgress.ready, false);
  assert.equal(inProgress.code, "uploading");
  assert.match(inProgress.message, /already in progress/i);
});

test("collection readiness handles loading and empty responses", () => {
  const loading = getCollectionReadiness({
    state: "loading",
    collectionCount: 0,
    collectionId: "",
  });
  const empty = getCollectionReadiness({
    state: "ready",
    collectionCount: 0,
    collectionId: "",
  });

  assert.equal(loading.code, "loading");
  assert.equal(empty.code, "empty");
});

test("backend upload failure message is surfaced", () => {
  const message = getUploadErrorMessage(
    new Error("The file exceeds the 10485760-byte upload limit."),
  );

  assert.equal(message, "The file exceeds the 10485760-byte upload limit.");
  assert.match(getUploadErrorMessage(null), /try again/i);
});

test("failed ingestion response is not success", () => {
  const outcome = getUploadOutcome({
    id: "45e481eb-5c27-476f-914a-39834498a382",
    status: "failed",
  });

  assert.equal(outcome.kind, "failed");
  assert.equal(outcome.status, "failed");
  assert.match(outcome.message, /indexing failed/i);
});

test("processing ingestion response is not success", () => {
  const outcome = getUploadOutcome({
    id: "45e481eb-5c27-476f-914a-39834498a382",
    status: "processing",
  });

  assert.equal(outcome.kind, "processing");
  assert.match(outcome.message, /not searchable yet/i);
});

test("ready ingestion response is success", () => {
  const outcome = getUploadOutcome({
    id: "45e481eb-5c27-476f-914a-39834498a382",
    status: "ready",
  });

  assert.equal(outcome.kind, "success");
  assert.equal(outcome.status, "ready");
  assert.match(outcome.message, /stored, indexed and ready/i);
});

test("supported file types and size limit are preserved", () => {
  assert.equal(isSupportedFile("notes.txt"), true);
  assert.equal(isSupportedFile("report.PDF"), true);
  assert.equal(isSupportedFile("image.png"), false);
  assert.equal(isWithinUploadSizeLimit(MAX_UPLOAD_BYTES), true);
  assert.equal(isWithinUploadSizeLimit(MAX_UPLOAD_BYTES + 1), false);
  assert.equal(isWithinUploadSizeLimit(0), false);
});
