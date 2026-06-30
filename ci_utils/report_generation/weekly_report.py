import os
import json
import xml.etree.ElementTree as ET
from ci_utils.common.logger import get_logger

logger = get_logger(__name__)


def get_status(tc):
    if tc.find("failure") is not None or tc.find("error") is not None:
        return "FAILED", "red", "#ffcccc"
    if tc.find("skipped") is not None:
        return "SKIPPED", "orange", "#ffe6cc"
    return "PASSED", "green", "#ccffcc"


def format_time(val):
    try:
        return f"{float(val):.2f}s"
    except:
        return val


def main():

    job_url = os.getenv("JOB_URL", "N/A")
    nfs_version = os.getenv("NFS_VER", "N/A")
    ceph_version = os.getenv("CEPH_VER", "N/A")
    gpfs_version = os.getenv("GPFS_VER", "N/A")

    # ✅ Read JSON directly
    mapping_json = os.getenv("WORKLOAD_TEST_MAPPING", "{}")
    selected_json = os.getenv("SELECTED_WORKLOADS", "[]")

    try:
        workload_map = json.loads(mapping_json)
    except Exception:
        logger.error("Failed to parse WORKLOAD_TEST_MAPPING")
        workload_map = {}

    try:
        selected_workloads = json.loads(selected_json)
    except Exception:
        logger.error("Failed to parse SELECTED_WORKLOADS")
        selected_workloads = []

    logger.info("Selected Workloads: %s", selected_workloads)
    logger.info("Workload Map: %s", workload_map)

    xml_files = [
        "upstream-weekly-report.xml",
        "upstream-weekly-gpfs-report.xml"
    ]

    rows = []
    stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    idx = 1

    for xml_file in xml_files:

        if not os.path.exists(xml_file):
            continue

        tree = ET.parse(xml_file)
        root = tree.getroot()

        for tc in root.iter("testcase"):

            name = tc.attrib.get("name", "")

            if not any(w in name for w in selected_workloads):
                continue

            # ✅ Safe structured lookup
            entry = next(
                (val for func, val in workload_map.items() if func in name),
                {"name": name, "coverage": "", "comment": ""}
            )

            display = entry.get("name", name)
            coverage = entry.get("coverage", "")
            comment = entry.get("comment", "")

            status, color, bg = get_status(tc)
            time = format_time(tc.attrib.get("time", "0"))

            stats["total"] += 1
            stats[status.lower()] += 1

            rows.append(
                f"<tr style='background-color:{bg}'>"
                f"<td>{idx}</td>"
                f"<td style='word-break:break-word;'>{display}</td>"
                f"<td>{coverage}</td>"
                f"<td style='color:{color};font-weight:bold'>{status}</td>"
                f"<td>{time}</td>"
                f"<td>{comment}</td>"
                "</tr>"
            )

            idx += 1

    rows_html = "".join(rows)

    html = f"""
<h2>Weekly NFS Upstream Runs</h2>

<table border='1' cellpadding='6' cellspacing='0'>
<tr><td>Job</td><td><a href='{job_url}'>{job_url}</a></td></tr>
<tr><td>NFS-Ganesha</td><td>{nfs_version}</td></tr>
<tr><td>Ceph</td><td>{ceph_version}</td></tr>
<tr><td>GPFS</td><td>{gpfs_version}</td></tr>
</table>

<br>

<h3>Test Execution Summary</h3>
<table border='1' cellpadding='6' cellspacing='0'>
<tr><th></th><th>Count</th></tr>
<tr><td>Total Tests</td><td><strong>{stats['total']}</strong></td></tr>
<tr><td style='color:green'>Passed</td><td><strong style='color:green'>{stats['passed']}</strong></td></tr>
<tr><td style='color:red'>Failed</td><td><strong style='color:red'>{stats['failed']}</strong></td></tr>
<tr><td style='color:orange'>Skipped</td><td><strong style='color:orange'>{stats['skipped']}</strong></td></tr>
</table>

<br>

<h3>Test Results</h3>
<table border='1' cellpadding='6' cellspacing='0'>
<tr>
    <th>S.No</th>
    <th>Test Name</th>
    <th>NFS Coverage</th>
    <th>Status</th>
    <th>Time</th>
    <th>Comments</th>
</tr>
{rows_html}
</table>
"""

    with open("email_report.html", "w") as f:
        f.write(html)


if __name__ == "__main__":
    main()