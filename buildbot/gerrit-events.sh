while true; do
	ssh gandi-nfs-ganesha@review.gerrithub.io -p 29418 -i /root/.ssh/id_rsa gerrit stream-events
done
