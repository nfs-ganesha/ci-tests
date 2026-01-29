## Sanity Dev CI – Quick Onboarding Guide

### Overview

- **Goal**: Run and develop CI tests for **NFS-Ganesha** using the `sanity_dev` Jenkins job.
- **Key pieces**:
  - `jobs/jjb/dev_sanity.yaml` – defines the Jenkins job & parameters.
  - `jobs/Jenkinsfile.sanity_dev` – actual pipeline (checkout, install, run tests).
  - `tests/dev_space/` – dev-focused pytest suites (e.g. `test_fsal.py`).
  - `ci_utils/` – shared Python helpers.
  - `ci_utils/dev_space/` – dev-only helpers (dependencies, node reservation, etc.).
- **Sanity dev pipeline**: [`dev-sanity-tests` Jenkins job](https://jenkins-nfs-ganesha.apps.ocp.cloud.ci.centos.org/view/all/job/dev-sanity-tests/)

---

## How the Jenkins Job Works

- **Job definition (`dev_sanity.yaml`)**
  - **Defines parameters**:
    - **`TEST_SUITE`**: which test file to run (e.g. `test_fsal` → `test_fsal.py`).
    - **`SERVER_NODE_COUNT`**, **`CLIENT_NODE_COUNT`**: how many nodes to reserve.
    - **`GIT_REPO`/`GIT_BRANCH`**: NFS-Ganesha source to test.
    - **`CMAKE_FLAGS`**, **`CMAKE_OVERRIDE`**: extra/override CMake options.
    - **`CENTOS_VERSION`**, **`CENTOS_ARCH`**: OS/arch to use.
  - **Points to pipeline**: uses `jobs/Jenkinsfile.sanity_dev` from this repo.

- **Pipeline (`Jenkinsfile.sanity_dev`)**
  - **Checks out**:
    - CI repo → `ci-tests/`
    - NFS-Ganesha → `nfs-ganesha/` (with submodules).
  - **Installs deps** from `ci_utils/requirements.txt`.
  - **Runs pytest**:
    - `pytest -v -s ci-tests/tests/dev_space/${TEST_SUITE}.py`
    - Uses `PYTHONPATH=ci-tests` so `ci_utils.*` imports work.

---

## Where to Put Code

- **Common/shared helpers**: `ci_utils/`
  - Logging, remote sessions, Ceph/Ganesha setup, Cthon/PyNFS managers, etc.
- **Dev-only helpers**: `ci_utils/dev_space/`
  - `dependencies.py`: install build/runtime deps on nodes.
  - `node_reservation.py`: reserve/release nodes.
- **Dev test suites**: `tests/dev_space/`
  - Example: `test_fsal.py` – builds Ganesha, brings up CephFS, runs Cthon + PyNFS.

---

## Test Flow in `tests/dev_space/test_fsal.py` (Pattern to Follow)

- **Inputs from Jenkins**:
  - Reads env vars: `TEST_SUITE`, `SERVER_NODE_COUNT`, `CLIENT_NODE_COUNT`, `CMAKE_FLAGS`, `CMAKE_OVERRIDE`, `CENTOS_VERSION`, `CENTOS_ARCH`.
- **Session-level fixtures (auto-used)**:
  - **`ci_params`**: parses env vars into a dict.
  - **`reserved_nodes`**: calls `reserve_nodes()` / `delete_nodes()` once per run.
  - **`remote_sessions`**: opens SSH (`RemoteSession`) to servers/clients.
  - **`cmake_config` + `cmake_flags`**:
    - Loads flags from `ci_utils/config/cmake_flags.yml`.
    - Merges with `CMAKE_FLAGS`, respects `CMAKE_OVERRIDE`.
- **Tests**:
  - **`test_cephfs_fsal`**: copy Ganesha to server, build with CMake flags, assert build success.
  - **`test_bringup_cephfs`**: `make install`, setup CephFS + Ganesha, assert setup.
  - **`test_cthon`**: run Cthon tests from client.
  - **`test_pynfs`**: run PyNFS tests from client.

Use this pattern (fixtures + managers from `ci_utils`) for any new dev tests.

---

## Typical Dev Workflow

- **To run via Jenkins**:
  - Open **`dev-sanity-tests`** job.
  - Set:
    - **`TEST_SUITE`**: e.g. `test_fsal`.
    - **Node counts**: `SERVER_NODE_COUNT`, `CLIENT_NODE_COUNT`.
    - **Repos/branches**: change `GIT_REPO`/`GIT_BRANCH` if testing your fork.
    - Optional: `CMAKE_FLAGS` / `CMAKE_OVERRIDE`, `CENTOS_VERSION`.
  - Start build, inspect:
    - “Checkout CI Tests” → “Checkout NFS-Ganesha” → “Install Dependencies” → “Run tests”.

---

## How to Add a New Dev Test Suite

- **1. Add a test file** under `tests/dev_space/`
  - Example: `tests/dev_space/test_newbackend.py`.
  - Reuse fixtures from `test_fsal.py`:
    - `ci_params`, `reserved_nodes`, `remote_sessions`, `cmake_flags`.
  - Use `ci_utils` helpers to:
    - Reserve nodes, connect via SSH, setup backends, run tests.

- **2. Wire it up in Jenkins**
  - In `jobs/jjb/dev_sanity.yaml`:
    - Add your test suite name to `TEST_SUITE` choices (e.g. `'test_newbackend'`).
  - In `jobs/Jenkinsfile.sanity_dev`:
    - Make sure `pytest` call matches the pattern:
      - `ci-tests/tests/dev_space/${params.TEST_SUITE}.py`.
    - Optionally expand the `suiteFileMap` for logging.

- **3. Optional: add CMake flags**
  - Edit `ci_utils/config/cmake_flags.yml`:
    - Add `tests: test_newbackend: [...]` for per-test flags.
