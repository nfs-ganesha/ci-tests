WORKING_DIR="~/WORKSPACE/DOWNLOAD_STORAGE_SCALE"
mkdir -p ~/WORKSPACE/DOWNLOAD_STORAGE_SCALE
cd $WORKING_DIR
yum install -y unzip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -qq awscliv2.zip
sudo ./aws/install
aws configure set aws_access_key_id ${AWS_ACCESS_KEY}
aws configure set aws_secret_access_key ${AWS_SECRET_KEY}
aws s3api get-object --bucket nfsganesha-ci --key "Storage_Scale_Developer-5.1.8.0-x86_64-Linux.zip" "Storage_Scale_Developer-5.1.8.0-x86_64-Linux.zip" 
ls -ltr ${WORKING_DIR}
cat Storage_Scale_Developer-5.1.8.0-x86_64-Linux.zip
