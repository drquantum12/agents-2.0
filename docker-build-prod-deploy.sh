#!/bin/bash

sudo docker buildx build --platform linux/amd64 -t gcr.io/nyaaysakha/vijayebhav-v2-device-prod .

sudo docker tag gcr.io/nyaaysakha/vijayebhav-v2-device-prod asia-south1-docker.pkg.dev/nyaaysakha/ollama-repo/vijayebhav-v2-device-prod

sudo docker push asia-south1-docker.pkg.dev/nyaaysakha/ollama-repo/vijayebhav-v2-device-prod

# Set RAZORPAY_MODE=test or live before running this script
export RAZORPAY_MODE=live

if [ "$RAZORPAY_MODE" = "live" ]; then
  RZP_KEY_ID="rzp_live_SnxwUgi7h6NUxE"
  RZP_KEY_SECRET="dxClpbZm62FDSBKDwGGQ6dTQ"
  RZP_WEBHOOK_SECRET="VIJAYEBHAV"
  ENABLE_AUTH="true"
else
  RZP_KEY_ID="rzp_test_SquU025kYvEIES"
  RZP_KEY_SECRET="qlhjXjbhQ0gOYlucsOQUTXpd"
  RZP_WEBHOOK_SECRET="VIJAYEBHAV"
  ENABLE_AUTH="false"
fi

gcloud run deploy vijayebhav-v2-device-prod \
--image asia-south1-docker.pkg.dev/nyaaysakha/ollama-repo/vijayebhav-v2-device-prod \
--region asia-south1 \
--platform managed \
--allow-unauthenticated \
--timeout 3600 \
--memory 4Gi \
--no-cpu-throttling \
--cpu-boost \
--min-instances 0 \
--execution-environment gen2 \
--concurrency 80 \
--set-env-vars RAZORPAY_KEY_ID="$RZP_KEY_ID",RAZORPAY_KEY_SECRET="$RZP_KEY_SECRET",RAZORPAY_WEBHOOK_SECRET="$RZP_WEBHOOK_SECRET",ENABLE_AUTH="$ENABLE_AUTH"