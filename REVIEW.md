# Data-integrity review

Reviewed the fetch → metrics → summary → HTML/plain-text → delivery → snapshot
path against the production source baseline `9ba2986`.

## Confirmed defects corrected

- Exhausted API failures were swallowed and presented as no games/rating data.
- Independent game queries could disagree; head-to-head and tables did not
  necessarily share the same evidence.
- In-progress scores could be credited as completed results, and ties could
  invent a winner.
- Summary/headline prose could contradict scores or favor a different metric
  without saying so. The delivery boundary now generates both from the data.
- AP fallback rankings were labeled CFP, missing polls looked like zero ranked
  teams, and fallback week/poll provenance was lost.
- Elapsed-week arithmetic mislabeled November 1 as week 10; the actual CFBD
  calendar identifies regular-season week 9.
- Partial ratings looked like full-conference/OOC averages; missing and zero
  values were confused in comparisons and historical deltas.
- Tied records received misleading winner/loser highlighting.
- Past unplayed games and missing ratings could skew upcoming-game selection.
- Postseason week 1 could sort before regular week 15 and overwrite its
  regular-season snapshot key.
- Separate conference snapshot commits could leave incomplete history. New
  pairs are atomic; legacy history is retained unchanged and not compared
  against the new metric semantics.
- Provider-supplied text and tooltip apostrophes were not consistently escaped
  in HTML. Subject/header and recipient validation now rejects invalid input.
- Test runs lacked an early empty-recipient guard and could initialize history.
  A dry-run mode now supports report review without mail or database writes.
- `TimeZone` is not a systemd timer property. The source calendar expression now
  embeds `America/New_York`. Duplicated file logging is avoided by leaving file
  logging to the application and routing unit stdout/stderr to the journal.

## Validation

- 60 offline unit/integration tests pass on macOS/Python 3.14 and in disposable
  OptiPlex Linux/Python 3.12.3 storage, including failure injection on the second
  snapshot insertion and simulated Gmail delivery failure. Linux test execution
  used a sanitized environment without production credentials.
- Python compilation and `git diff --check` pass.
- Recorded real CFBD responses replay successfully through the complete fetch,
  validation, metrics, narrative and dual email rendering flow: 16 SEC teams,
  18 Big Ten teams, SEC head-to-head 2–1, AP week 9 counts 9 and 5.
- Native `systemd-analyze verify` accepts both revised units in disposable
  OptiPlex temporary storage, without installing or starting either unit.
- Native calendar validation confirms November 1 at 07:00 EST (12:00 UTC) and
  November 8 at 07:00 EST. No installed schedules were changed.
- GitHub rejected the optional new Actions workflow because the existing OAuth
  connection lacks workflow-file scope. No workflow is added and credential
  permissions are unchanged. All tests remain in the repository and can be run
  directly without mail/data credentials.

## Limits and rollout

Upstream errors cannot be ruled out merely by internal consistency. This code
rejects detected incomplete/conflicting evidence and does not guarantee that a
provider's mutually consistent records are factually perfect. Reports use the
latest season data, not an as-of historical-week reconstruction.

Gmail delivery and SQLite cannot commit atomically; an ambiguous send outcome
or history-write failure after successful delivery requires review before a
retry. No automatic send retry is introduced.

Changes are source-only. Deploying the source, updating installed units,
reloading systemd, or sending a corrected digest are separate operational
steps. Existing databases, credentials, live services and timers were not changed
by this review. Native validation used disposable unit files only.
