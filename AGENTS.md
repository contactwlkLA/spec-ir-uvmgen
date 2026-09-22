# Conventions

Revision: 4
Date: 2026-08-31
Time: 15:02 PDT

Revision history:
- Rev 1 (2026-08-18): template adopted from an external project.
- Rev 3 (2026-08-30): renumbered to this workspace; added scheme-precedence
  clause; clarified <dir> as the sessions/ workspace number, autonomous of
  git-worktree parentage.
- Rev 4 (2026-08-31): added Execution Gate — state the authorizing gate
  before any working-tree change; an open question freezes all edits.

All official docs, README, PRDs, etc. must carry a revision number, date, and time.

Revision number = <dir>.<session>:
- <dir> = the workspace directory number under sessions/ (this workspace: "3").
  Each sessions/<N> directory is an autonomous workspace; git-worktree
  parentage (sessions/3 checked out from sessions/2) does not change <dir>.
- <session> = working session number, "0" being the initial one; it increments per new session.
- The edit-letter suffix is dropped.
- Relatively static documents may use <dir> alone (e.g., "3").

Scheme precedence: a document that already carries its own project-specific
revision scheme keeps that scheme. In this workspace, `uvm_buffer_prd.md`
(the authoritative DUT PRD) and its derived artifacts are versioned by the
v0.0X letter scheme tracked in its §9 Revision History; the <dir>.<session>
scheme applies to every other official document.

Directory <private>, <Downloads> are forbidden to enter.
 # ==================================================================
## Execution Gate

Gate discipline (applies to every working-tree change — code, docs, renames,
regeneration): before making it, state which gate or user instruction
authorizes it. A question asked and not yet answered freezes all edits — an
open question is a held gate, not a passed one. If no gate applies, stop and
request one. Read-only verification is exempt.

## Commit Flow

Use this flow whenever a work item appears complete. Do not skip gates or combine approval questions.

### 1. Documentation Sync Gate

1. Inspect the completed changes and identify every affected document, including the PRD, architecture/specification, schemas, configuration examples, README, changelog, and operational instructions.
2. Update only the documents affected by actual behavior or contract changes.
3. Check terminology, filenames, versions, dates, schemas, and cross-references for consistency.
4. Do not promote the revision automatically.
5. Report:
   - documents updated;
   - documents reviewed but unchanged;
   - proposed next revision and justification.
6. Ask: **“Promote these documents to the next revision?”**
7. Stop and wait.
8. If approved, update the revision, timestamp, status, and revision history, then repeat the consistency check.

### 2. Audit Gate

1. Audit the final code-and-document diff against:
   - approved requirements;
   - schemas and interfaces;
   - acceptance criteria;
   - relevant tests;
   - security, privacy, and failure contracts.
2. Run the minimum relevant verification. Any failed required check is blocking.
3. Report each gap with:
   - severity;
   - evidence;
   - affected files;
   - proposed fix;
   - consequence of deferral.
4. If gaps exist, ask: **“Fix these gaps now, explicitly defer the non-blocking gaps, or abort?”**
5. Stop and wait.
6. If fixing, return to the Documentation Sync Gate after implementation.
7. Blocking gaps and failed tests may not be deferred into a commit.
8. Proceed only when the audit is clean or the user explicitly accepts documented non-blocking gaps.

### 3. Commit Gate

1. Show:
   - final `git status --short`;
   - exact files proposed for staging;
   - concise diff summary;
   - verification results;
   - proposed commit message;
   - any explicitly accepted deferred gaps.
2. Ask: **“Commit these exact files with this message?”**
3. Stop and wait.
4. After approval:
   - stage only the listed paths; never use an ambiguous `git add`;
   - run `git diff --cached --check`;
   - verify the staged diff contains no unrelated changes;
   - create the commit;
   - report the commit hash, subject, and final working-tree status.
5. Do not amend, push, tag, or create another commit without separate authorization.


keep module testing to a minimal, that is creating a  module to test a functional module should be kept to be a minimum.
