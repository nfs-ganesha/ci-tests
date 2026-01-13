import os

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

class AWSSetupForGPFS:
    def __init__(self, session, aws_repo, aws_region="ap-south-1"):
        """
        Handles system package installations and AWS CLI setup.
        Args:
            session (RemoteSession): Remote session to the target machine.
            aws_repo (str): URL to download AWS CLI.
            aws_region (str): AWS region for configuration.
        Raises:
            RuntimeError: If AWS credentials are not found in environment variables.
        """
        self.session = session
        self.aws_region = aws_region
        self.aws_access_key = os.environ.get("ACCESS_KEY")
        self.aws_secret_key = os.environ.get("SECRET_KEY")
        self.aws_repo = aws_repo
        if not self.aws_access_key or not self.aws_secret_key:
            raise RuntimeError("AWS credentials not found in environment variables")

    # -----------------------
    # AWS CLI Setup
    # -----------------------
    def setup_aws_cli(self):
        logger.info("[STEP]: Setting up AWS CLI on the remote machine")
        aws_zip = "awscliv2.zip"
        run_cmd(self.session, f"curl '{self.aws_repo}' -o '{aws_zip}'")
        run_cmd(self.session, f"unzip -qq {aws_zip}")
        run_cmd(self.session, "chmod +x ./aws/*")
        run_cmd(self.session, "./aws/install")
        run_cmd(self.session, "aws --version")
        run_cmd(self.session, f"aws configure set aws_access_key_id {self.aws_access_key}")
        run_cmd(self.session, f"aws configure set aws_secret_access_key {self.aws_secret_key}")
        run_cmd(self.session, f"aws configure set default.region {self.aws_region}")


    # -----------------------
    # Fetch Versioned Object from S3
    # -----------------------
    def fetch_versioned_object(self, bucket="centos-ci", version_file="version_to_use.txt"):
        logger.info("[STEP]: Fetching versioned object from S3 bucket: %s", bucket)
        
        run_cmd(self.session, f"aws s3api get-object --bucket {bucket} --key {version_file} {version_file}")
        output, _ = run_cmd(self.session, f"cat {version_file}")
        version_to_use = output.strip()
        logger.info("Version to use: %s", version_to_use)

        run_cmd(self.session, f"aws s3api get-object --bucket {bucket} --key {version_to_use} {version_to_use}")

        return version_to_use