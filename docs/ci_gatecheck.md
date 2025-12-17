## CI Tests – Onboarding (Gatecheck, Checkpatch/FSAL, PyNFS/Cthon)

### 1. What this pipeline does

- **Goal**: Validate an NFS-Ganesha patch with:
  - **Checkpatch** (style/lint)
  - **Clang-format** (formatting)
  - **FSAL build tests** (CephFS, VFS, RGW, GPFS)
  - **Cthon & PyNFS** protocol tests (separate job / test file)
- **Key pieces**:
  - `jobs/Jenkinsfile.gatecheck` – Jenkins pipeline for gatecheck.
  - `tests/test_checkpatch_fsal.py` – Checkpatch, Clang, FSAL build tests.
  - `tests/test_pynfs_cthon.py` – Cthon & PyNFS tests across backends.
  - `ci_utils/*` – shared helpers for node handling, logging, remote sessions, NFS-Ganesha/FS backends, etc.
- **Gatecheck pipeline**: [`Jenkinsfile.gatecheck` Jenkins job](https://jenkins-nfs-ganesha.apps.ocp.cloud.ci.centos.org/job/gatecheck-trigger-gerrithub/)

---

## 2. Jenkins gatecheck pipeline (`jobs/Jenkinsfile.gatecheck`)

- **Pre-flight**:
  - Uses `preCheckGerritPatchset()` to:
    - Query Gerrit for the latest patchset and mergeability.
    - Abort the build (with a Gerrit message) if:
      - A newer patchset exists, or
      - The change is not mergeable.
- **Install dependencies**:
  - Installs Python + CI dependencies from `ci_utils/requirements.txt`.
- **Run tests**:
  - Reserves nodes:
    - `pytest -v -s ci-tests/tests/test_reserve_nodes.py`
  - CI pre-reqs and environment:
    - `pytest -c ci-tests/ci_utils/pytest.ini -v -s -m checkpatch_fsal ci-tests/tests/test_ci_pre_req.py`
  - Checkpatch / Clang / FSAL build:
    - `pytest -v -n 6 --capture=no --junitxml=report-checkpatch-fsal.xml ci-tests/tests/test_checkpatch_fsal.py`
- **Teardown & Gerrit reporting**:
  - Always:
    - `pytest -v -s ci-tests/tests/test_delete_nodes.py`
    - Cat failure/summary files under `${WORKSPACE}/failures` and summaries.
  - Uses `postToGerrit(...)` to:
    - Post a summary message and, if checkpatch/clang JSON is present, inline comments.
    - Adjust `Verified` label (e.g., `-1` if there are many comments).

**As a dev**: You typically don’t change this pipeline flow often; you extend tests and `ci_utils` and only tweak the pipeline for new stages or flags.

---

## 3. Checkpatch, Clang, FSAL tests (`tests/test_checkpatch_fsal.py`)

### 3.1. Common fixtures

- **Workspace & files**:
  - Uses `WORKSPACE` (defaults `/tmp`) and:
    - `duffy_session.json` – reserved nodes info.
    - `failures/` – JSON/log files.
    - `summary_checkpatch_fsal.txt`, `summary_status.txt` – human-readable + status summary.
- **`server_node` (session fixture)**:
  - Reads first node IP from `duffy_session.json`.
- **`create_session` (test fixture)**:
  - Connects via `RemoteSession` to `server_node`.
  - Creates a per-test directory `/root/<test_name>`.
  - Copies `${WORKSPACE}/nfs-ganesha` to the remote test dir.
- **`cmake_config` / `cmake_flags`**:
  - Loads `ci_utils/config/cmake_flags.yml`.
  - Merges:
    - `default` + per-test flags + `CMAKE_FLAGS` env.
  - `CMAKE_OVERRIDE` env can bypass YAML and use only env flags.
- **`attach_test_name`**:
  - Sets the current test name in logger for consistent logs.

### 3.2. Tests

- **`test_checkpatch`**:
  - Copies `build_scripts/checkpatch/checkpatch-to-gerrit-json.py` to remote.
  - Runs:
    - `git show --format=email HEAD~0` through `checkpatch.pl`.
    - Pipes into `checkpatch-to-gerrit-json.py` to produce JSON.
  - Handles:
    - `Checkpatch OK` → success.
    - Otherwise:
      - Parses JSON comments, drops exclusions (e.g. `/COMMIT_MSG`).
      - Writes `checkpatch_logs.json` when failing.
      - Flattens messages for Gerrit and writes summary (via `gerrit_custom_message`).

- **`test_clang_format`**:
  - Copies `build_scripts/clang/clangformat_to_gerrit_json.py`.
  - Runs:
    - `git clang-format` diff with `.clang-format`, pipes into converter script.
  - On failure:
    - Writes JSON and text logs under `failures/`.
    - Logs a Gerrit-friendly summary (again via `gerrit_custom_message`).

- **FSAL build tests** (e.g. CephFS):
  - Use `create_session` + `cmake_flags` to:
    - Configure and build NFS-Ganesha (e.g. CephFS FSAL).
    - Log summary and status to `summary_checkpatch_fsal.txt` / `summary_status.txt`.

**As a dev**:
- To **add new lint/build checks**:
  - Add a new test function using `create_session`, and:
    - Run required tools on the remote workspace.
    - Write failures to a JSON/log under `${WORKSPACE}/failures`.
    - Call `gerrit_custom_message(code, "<Your check name>", out)`.

---

## 4. Cthon & PyNFS tests (`tests/test_pynfs_cthon.py`)

### 4.1. Common fixtures

- **Nodes and workspace**:
  - `SESSION_FILE` (`duffy_session.json`) and `BAREMETAL_SESSION_FILE` for reserved/baremetal nodes.
  - `FAILURE_FILE`, `SUMMARY_FILE`, `SUMMARY_STATUS` under `${WORKSPACE}`.
- **`all_nodes` / `all_baremetal_nodes`**:
  - Read node lists from the session files.
- **`create_session`**:
  - Parameterized fixture:
    - Accepts indices (e.g. `1` or `[0, 2]`).
    - Supports `@pytest.mark.baremetal` to pick from baremetal list.
  - For each requested node:
    - Opens `RemoteSession` with a per-test directory (`/root/<test_name>_<idx>`).
    - Copies `${WORKSPACE}/nfs-ganesha` to that dir.
  - Yields:
    - Single tuple `(session, default_dir, node_ip)` or list of tuples.
- **`cmake_config` / `cmake_flags`**:
  - Same YAML + env merging pattern as in `test_checkpatch_fsal.py`.

### 4.2. Tests (examples)

- **`test_cthon_cephfs`**:
  - Node allocation: 1 server.
  - Steps:
    - Build & install NFS-Ganesha with CephFS flags.
    - Run `CephGaneshaSetup` → CephFS volume.
    - Run `GaneshaManager` → exports.
    - Use `CthonManager` to clone/build Cthon and run tests (skip NFSv3).
    - On failure:
      - Save Cthon logs to `failures/cthon_logs.txt`.
      - Write summary entry (pass/fail) to `SUMMARY_FILE` / `SUMMARY_STATUS`.

- **`test_pynfs_cephfs`**:
  - Node allocation: `[0, 2]` (client, server).
  - Steps:
    - Build & install NFS-Ganesha on server node.
    - Use `CephGaneshaSetup` + `GaneshaManager(test_type="pynfs")`.
    - On client node:
      - Use `PyNFSManager` to run tests against export `/nfs/cephfs` or similar.
    - Log failures and summary exactly as above.

- **Other tests in this file** follow a similar pattern for:
  - Different backends (**VFS, GPFS**, etc.).
  - Virtual machine flows via `VMManager`.
  - Additional Cthon/PyNFS combinations.

**As a dev**:
- To **add a new protocol/backend test**:
  - Add a new test function reusing:
    - `@pytest.mark.parametrize("create_session", [...], indirect=True)`
    - `@pytest.mark.parametrize("cmake_flags", ["<flag-set>"], indirect=True)`
  - Use the appropriate `ci_utils` manager:
    - `CephGaneshaSetup`, `GPFSGaneshaManager`, `VFSGaneshaManager`, `VFSVolumeExporter`, `PyNFSManager`, `CthonManager`, `VMManager`.
  - Follow existing pattern for:
    - Build/install.
    - Backend setup and export.
    - Running Cthon/PyNFS/other workloads.
    - Logging to `FAILURE_FILE` and summary files.

---

## 5. Where to put shared code and how to extend

- **Shared logic**:
  - Always prefer adding helpers in `ci_utils`:
    - Node handling: `ci_utils/common`, `ci_utils/dev_space`, GPFS/Ceph/VFS setup modules, NFS-Ganesha managers.
    - Utilities: `remote_session.py`, `helpers.py`, `logger.py`, backend setup modules.
- **Extending tests**:
  - For **new lint/static checks** → extend `tests/test_checkpatch_fsal.py`.
  - For **new backend or protocol flows** → extend `tests/test_pynfs_cthon.py`.
  - Respect:
    - Existing fixtures (no custom SSH logic if not needed).
    - Summary/JSON log pattern so `Jenkinsfile.gatecheck` and Gerrit integration keep working.
